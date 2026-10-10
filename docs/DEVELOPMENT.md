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

## 上传与后续更新

```bash
git status
git push -u origin main
```

如远端已有提交，先 `git fetch origin` 并审阅远端历史，再合并后推送；不要强制覆盖。
新机器可以按照根目录 README 的 clone 和安装步骤构建。构建产物不进入 Git，避免绑定本机路径
或发布仅兼容特定系统的二进制文件。
