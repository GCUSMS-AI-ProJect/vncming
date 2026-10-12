# VNCMing

Linux VNC 远程桌面客户端：GTK 连接管理界面 + 定制 TigerVNC 原生客户端。
橙色主题，Ubuntu 窗口按钮，圆角输入框和弹窗，带悬停、按压及打开动画。

- 新建连接置顶，用户名与地址相同时更新已有记录，★ 标记最近保存的连接。
- 双击列表编辑名称、IP地址、用户名和密码；每行可直接连接或删除。
- 密码保存在系统钥匙环，使用私有管道传给客户端，不写入连接配置或命令行。
- 默认最大化窗口，保留标题栏和桌面面板；远程分辨率随窗口调整，服务器不支持时使用本地缩放，并同步鼠标坐标。
- F8 打开远程连接菜单，可切换全屏、查看连接信息和修改连接选项。
- 全屏时默认请求远程分辨率 1920×1080（需要服务器支持动态分辨率）；画面仍自适应本地屏幕。
- 窗口模式也默认固定远程分辨率为 1920×1080，窗口缩放只改变本地显示；可在连接选项取消固定。

## Clone 和安装

目前支持 Linux X11 桌面，已在 Ubuntu 22.04 / GNOME 42 验证。

```bash
git clone https://github.com/GCUSMS-AI-ProJect/vncming.git
cd vncming
./scripts/install-deps.sh
./install.sh
./vncming
```

依赖安装脚本使用 `sudo apt`。程序及桌面入口按当前用户安装，无需以 root 运行程序。
`install.sh` 会自动构建缺失的客户端，安装后可从 Show Applications 启动，也可运行
`~/.local/bin/vncming`。启动器直接使用此 clone 目录内的程序，修改源码后重新构建即可生效。
移动或重命名 clone 目录后，重新执行 `./install.sh` 更新启动路径。

仅构建及运行：

```bash
./scripts/build.sh
./vncming
```

## DEB 安装包

在 Ubuntu 22.04 amd64 上构建并安装：

```bash
./scripts/install-deps.sh
./scripts/build-deb.sh
sudo apt install ./dist/vncming_1.0.3_amd64.deb
vncming
```

安装包包含编译好的客户端、GTK 界面、橙色图标、应用菜单入口及对应源码，
安装时自动处理运行依赖，无需在目标机器编译。包安装到 `/usr/lib/vncming`，
命令入口为 `/usr/bin/vncming`；卸载可运行 `sudo apt remove vncming`，个人连接配置和钥匙环不会删除。
源码内保留打包脚本，可用 `./scripts/build-deb.sh --version 1.0.4` 构建新版本。

本机若已运行 `./install.sh`，用户级菜单入口与 `~/.local/bin/vncming` 会继续使用源码目录。
可用 `/usr/bin/vncming` 明确启动 DEB 版本。不要用 root 启动图形界面。
包内也附带可选的 GNOME 42 应用列表扩展，重新登录后可运行
`gnome-extensions enable vncming-app-grid@local` 启用；其他 GNOME 版本无需启用。

## 连接与配置

地址支持 `192.168.1.100`、`pi.local`、`pi.local:1`（显示编号）、
`pi.local::5901`（TCP 端口）、`vnc://pi.local:5901`。

连接配置存放于 `~/.config/vncming/connections.json`，密码保存在 GNOME Keyring。
安装器会迁移已有的 `~/.config/tigervnc-classic/connections.json`，钥匙环条目继续使用。
应用需要运行中的桌面会话及系统钥匙环服务。

编辑连接时可勾选“自动继续证书主机名不匹配提示”，只对该连接地址生效；其他证书检查仍保留。
项目源码不包含任何个人连接地址、账号、密码或受信任服务器配置。

## 收藏后仍显示在应用列表

GNOME 42 会从应用列表隐藏已收藏的应用，可选安装本项目的 VNCMing 专用扩展：

```bash
./install.sh --gnome-grid
# 重新登录桌面后：
gnome-extensions enable vncming-app-grid@local
gsettings set org.gnome.shell disable-user-extensions false
```

其他 GNOME 版本使用普通桌面入口，不安装这个仅支持 GNOME 42 的扩展。

## 源码目录

```text
app/                    GTK 启动界面、主题、动画和钥匙环逻辑
vendor/tigervnc/         定制 TigerVNC 1.12.0 完整源码及第三方许可证
assets/                 应用图标
scripts/                构建、安装及检查脚本
tests/                  原生弹窗、认证、保存连接、缩放和鼠标坐标回归验证
integrations/gnome-shell/ 可选 GNOME 42 扩展
docs/                   维护说明与界面预览
build/                  本机构建和验证产物，不进入 Git
vncming                 项目启动入口
install.sh              当前用户安装入口
```

维护、测试和发布说明见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 许可证及来源

代码遵循 [GNU GPL v2](LICENSE)。原生客户端基于 TigerVNC 1.12.0，完整源码已包含在
`vendor/tigervnc/`，无需额外下载源码或 Git 子模块。原有版权及第三方许可文件保留。
图标沿用 VNCMing 的 VNC 字样图案，视觉参考来自 USTC Vlab 的 VNC 教程；图案来源说明保留于
[NOTICE.md](NOTICE.md)。
