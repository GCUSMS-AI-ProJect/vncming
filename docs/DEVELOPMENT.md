# 开发及发布

## 修改与启动

`app/viewer.py` 管理列表、编辑、启动进程、进度和超时；`app/credentials.py` 使用 Secret
Service；`app/theme.css` 与 `app/motion.py` 管理 GTK 样式及动画。
原生 UI、全屏、XRender 缩放和鼠标坐标代码位于 `vendor/tigervnc/vncviewer/`。
`MacMotion.h` 是当前共享原生控件与动画实现，`StyledMessage.h` 负责错误和确认弹窗。

```bash
./scripts/build.sh      # 修改原生 C++ 后构建
./scripts/check.sh      # 不需要桌面的基础检查
./vncming              # 使用本目录程序启动
```

Python 与 CSS 修改后重开启动界面；原生客户端修改后重连。已打开的旧进程不会自动替换。

## 回归验证

测试使用本机模拟 RFB 服务器和虚构凭据。GTK / 原生 UI 测试需要当前 X11 桌面、
`xdotool`、`xwininfo` 和 GNOME Keyring；不要同时运行多个会操作桌面的 GUI 测试。
测试输出写入 `build/test-results/`，不提交截图或日志。

DEB 打包后可运行 `python3 tests/verify_deb.py` 检查完整性、依赖、桌面入口、
源码及解包后启动路径；附加 `--gui` 会使用临时配置短暂打开解包后的 GTK 界面。

```bash
sudo apt install xdotool x11-utils
/usr/bin/python3 tests/verify_saved_connection.py
/usr/bin/python3 tests/verify_ui.py
/usr/bin/python3 tests/verify_fit.py
/usr/bin/python3 tests/verify_motion.py
./vncming --theme-check
build/verify-native-messages
```

`verify_saved_connection.py` 的配置位于临时目录，虚构密码写入测试专用钥匙环条目并清理。
`verify_fit.py` 检查窗口缩放、完整画面、全屏状态及实际鼠标事件坐标。

`/usr/bin/python3 tests/verify_suggestions.py` 在 X11 桌面检查地址搜索下拉：IP
开头、中间、结尾片段匹配，名称匹配，键盘和鼠标选择，以及选中后复用已保存配置。
测试只使用临时配置与模拟连接记录，不访问真实连接或钥匙环；主题截图存入
`build/test-results/suggestions.png`。方向键选择，回车填入地址，Esc 收起下拉；
点击连接或再次回车才发起连接。

## 局部缩放绘制优化

FitToWindow 将 framebuffer 的更新区域映射到窗口，包含双线性插值所需的相邻像素，
不再因一个小区域更新而强制重绘整幅画面。XRender 合成使用目标裁剪；窗口重绘和
尺寸变化仍绘制完整画面。原尺寸显示直接走无缩放路径，跳过滤镜和变换设置。

运行 `sh scripts/check-rendering.sh` 检查放大、缩小、非整数比例、画面边缘、非零偏移、
连续局部更新和缩放后原尺寸绘制。局部画面与完整画面比较允许每通道 1 色阶的
XRender 插值舍入差异，更新区域外像素必须不变。`verify_fit.py` 另检查真正 RFB 局部更新。

脚本还测量 1920×1080 缩放到 1280×720、32×32 源区域更新的合成成本：300 次绘制，
五轮中位数，目标读回确保绘制完成。本机初测完整合成为 97.630 ms，局部为 18.391 ms，
包含读回开销；这是绘制微基准，不能代表网络延迟、树莓派性能或整体帧率。
整屏视频更新几乎无法从区域裁剪获益。实际结果取决于 X 服务、显卡及更新内容。

## 上传与后续更新

```bash
git status
git push -u origin main
```

如远端已有提交，先 `git fetch origin` 并审阅远端历史，再合并后推送；不要强制覆盖。
新机器可以按照根目录 README 的 clone 和安装步骤构建。构建产物不进入 Git，避免绑定本机路径
或发布仅兼容特定系统的二进制文件。

文件传输验证：

```sh
/usr/bin/python3 tests/verify_file_transfer.py
/usr/bin/python3 tests/verify_file_transfer_ui.py
```

第一个测试使用临时目录和本机 Paramiko SFTP 服务，验证双向文件夹、空目录、中文
名称、同名处理、取消、重试，以及未知/变化的 SSH 主机身份。第二个测试需要 X11，
使用临时本地端点验证 GTK 双栏导航、上传下载按钮、任务队列和登录布局；不读真实
钥匙环、不访问树莓派，预览存入 `build/test-results/file-transfer-preview.png`。
`verify_ui.py` 另外检查原生 F8 文件传输菜单向独立启动器传递正确的地址参数。

已连接界面的独立顶部工具栏提供“文件传输”按钮，远程画面从工具栏下方开始。
`verify_ui.py` 验证可见按钮、窗口缩放后位置、地址参数，以及按钮点击不会传递至
远端；添加 `--fullscreen` 可检查全屏状态。`verify_fit.py --toolbar` 验证工具栏
布局下的完整画面、增量缩放、远程分辨率及鼠标坐标映射。

目录浏览使用左右两栏各自的工作线程。远程浏览另外打开一个 SFTP session，
与文件传输共用已验证的 SSH 连接，但不共享 SFTP 请求状态。双击、返回和刷新
使用已确认的绝对路径，省去重复 REALPATH 请求；手动输入路径仍由服务器规范化。
列表元数据在后台准备，GTK 每次 idle 添加 100 行，完成后替换列表；文件和文件夹
SVG 按名称、尺寸缓存。目录内容不缓存，刷新仍读取真实文件系统。

文件传输测试还验证同一 SSH 连接上的双 SFTP session：传输在中途暂停时，另一个
session 可以读取目录。界面测试验证传输队列阻塞时仍能导航、过期请求及错误不会
覆盖当前目录，以及 1501 项目录只需要两次 SVG 解码。测试报告的本地加载耗时
不代表树莓派或 UU 远程的网络实测结果。
