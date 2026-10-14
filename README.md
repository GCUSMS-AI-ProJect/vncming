# VNCMing

适用于 Ubuntu / Linux X11 的 VNC 远程桌面客户端，基于 GTK 和 TigerVNC，采用简洁的橙色主题。

## 功能

- 输入 IP 连接，保存常用设备，支持名称与 IP 片段搜索。
- 管理连接名称、地址和账号，密码保存在系统钥匙环。
- 画面自适应窗口，支持全屏和固定远程分辨率，优化局部更新绘制。
- 已连接界面提供文件传输图标，支持双向文件与文件夹传输、任务队列和失败重试。

## 安装

已在 Ubuntu 22.04 / GNOME 42 的 X11 桌面验证。

```bash
git clone https://github.com/GCUSMS-AI-ProJect/vncming.git
cd vncming
./scripts/install-deps.sh
./install.sh
./vncming
```

依赖安装需要 `sudo`，程序以普通用户运行。安装后可从应用菜单启动。
移动源码目录后，重新运行 `./install.sh` 更新启动路径。

## 使用

地址示例：`192.168.1.100`、`pi.local`、`pi.local:1`（显示编号）、`pi.local::5901`（端口）。
双击已保存的连接可编辑；名称留空时使用 IP 地址。远控界面按 **F8** 打开菜单、切换全屏。

文件传输使用独立的 SSH/SFTP 连接，远端需要开启 SSH，默认端口为 **22**。
支持密码、密钥和 SSH Agent；首次连接需确认主机指纹。重试从头开始，不支持断点续传。
详细说明见 [文件传输](docs/FILE_TRANSFER.md)。

连接配置保存在 `~/.config/vncming/connections.json`，密码由系统钥匙环管理。

## 构建与维护

```bash
./scripts/build.sh      # 构建原生客户端
./scripts/check.sh      # 基础检查
./scripts/build-deb.sh  # 生成 DEB 安装包，输出到 dist/
```

开发、测试与发布说明见 [开发文档](docs/DEVELOPMENT.md)。

## 许可证

遵循 [GPL v2](LICENSE)，基于 TigerVNC 1.12.0，保留上游版权及第三方许可证。
图标来源见 [NOTICE.md](NOTICE.md) 和 [文件传输图标说明](assets/transfer/README.md)。
