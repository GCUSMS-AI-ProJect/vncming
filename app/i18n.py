"""Chinese and English UI strings. Keep user data and state tokens untranslated."""
import os
import weakref

LANGUAGES = ('system', 'zh_CN', 'en')
_preference = 'system'

def system_language(environ=None):
    env = os.environ if environ is None else environ
    messages = env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG') or 'C'
    # GNU gettext ignores LANGUAGE in the POSIX locale.
    value = messages if messages in ('C', 'POSIX') else env.get('LANGUAGE') or messages
    value = value.split(':', 1)[0].replace('-', '_').lower()
    return 'zh_CN' if value.startswith('zh') else 'en'

def configure(preference):
    global _preference
    _preference = preference if preference in LANGUAGES else 'system'

def language():
    return system_language() if _preference == 'system' else _preference

class Text(str):
    """A string carrying its translation recipe through formatting and concatenation."""
    def __new__(cls, render):
        instance = super().__new__(cls, render())
        instance.render = render
        return instance

    def __add__(self, other):
        return Text(lambda: self.render() + render(other))

    def __radd__(self, other):
        return Text(lambda: render(other) + self.render())

    def format(self, *args, **kwargs):
        return Text(lambda: self.render().format(
            *(render(value) for value in args),
            **{key: render(value) for key, value in kwargs.items()}))


def render(value):
    return value.render() if isinstance(value, Text) else value


def tr(message):
    if isinstance(message, Text):
        return message
    return Text(lambda: ENGLISH.get(message, message) if language() == 'en' else message)


_bindings = weakref.WeakKeyDictionary()


def _remember(widget, key, value):
    if isinstance(value, Text):
        if widget not in _bindings:
            _bindings[widget] = {}
            # Keep Python translation metadata on the GObject itself. GTK owns
            # many labels without any other Python reference to their wrapper.
            widget._vncming_translations = _bindings[widget]
            # GTK can retain a destroyed widget's Python wrapper until the next tick.
            if hasattr(widget, 'destroy'):
                widget.connect('destroy', lambda item: _bindings.pop(item, None))
        _bindings[widget][key] = value
    elif widget in _bindings:
        _bindings[widget].pop(key, None)


def create(constructor, *args, **kwargs):
    """Create a widget and bind only explicitly translated presentation properties."""
    widget = constructor(*args, **kwargs)
    for name, value in kwargs.items():
        _remember(widget, ('property', name.replace('_', '-')), value)
    if args and isinstance(args[0], Text):
        _remember(widget, ('property', 'title'), args[0])  # TreeViewColumn title
    return widget


def set_text(widget, method, *args):
    result = getattr(widget, method)(*args)
    name = method[4:].replace('_', '-')
    if method == 'set_text' and widget.find_property('label') is not None:
        name = 'label'
    key = ('icon-tooltip', args[0]) if method == 'set_icon_tooltip_text' else ('property', name)
    _remember(widget, key, args[-1])
    return result


def add_buttons(dialog, method, *args):
    result = getattr(dialog, method)(*args)
    for index in range(0, len(args), 2):
        button = dialog.get_widget_for_response(args[index + 1])
        _remember(button, ('property', 'label'), args[index])
    return result


def append_choice(widget, identifier, caption):
    widget.append(identifier, caption)
    _remember(widget, ('choice', identifier), caption)


def refresh():
    """Update existing widgets in place; entries, focus and running work stay intact."""
    for widget, properties in list(_bindings.items()):
        for (kind, name), value in list(properties.items()):
            text = value.render()
            if kind == 'property':
                widget.set_property(name, text)
            elif kind == 'icon-tooltip':
                widget.set_icon_tooltip_text(name, text)
            elif kind == 'choice':
                for row in widget.get_model():
                    if row[1] == name:
                        row[0] = text
                        break

def native_environment(environment, locale_directory):
    environment = environment.copy()
    environment['VNCMING_LANGUAGE'] = language()
    environment['VNCMING_LOCALEDIR'] = str(locale_directory)
    environment['LANGUAGE'] = language()
    # C.UTF-8 exists on supported Ubuntu releases and permits LANGUAGE override.
    environment['LC_ALL'] = 'C.UTF-8'
    return environment

ENGLISH = {
    '文件': 'File',
    '查看': 'View',
    '帮助': 'Help',
    '新建': 'New',
    '文件传输…': 'File Transfer…',
    '退出': 'Quit',
    '连接选项…': 'Connection Options…',
    '关于': 'About',
    'IP地址或主机名': 'IP address or hostname',
    '地址': 'Address',
    '输入地址或搜索连接': 'Enter an address or search connections',
    '连接': 'Connect',
    '我的连接': 'My Connections',
    '名称': 'Name',
    'IP地址': 'IP Address',
    '连接到你的电脑': 'Connect to your computer',
    '新建一个连接，或在上方输入 IP 地址直接访问': 'Create a connection, or enter an IP address above',
    '新建连接': 'New Connection',
    '好': 'OK',
    '请输入 IP 或主机名，例如 192.168.1.100；指定端口用 192.168.1.100::5901。': 'Enter an IP address or hostname, e.g. 192.168.1.100. For a port, use 192.168.1.100::5901.',
    '端口或显示编号超出有效范围。': 'The port or display number is out of range.',
    '无法保存连接：': 'Unable to save connection: ',
    '双击编辑连接，或右键打开操作菜单': 'Double-click to edit, or right-click for actions',
    '最近保存': 'Latest',
    '最新保存的连接': 'Most recently saved connection',
    '删除连接：': 'Delete connection: ',
    '正在连接，请稍候': 'Connecting, please wait',
    '连接到此设备': 'Connect to this device',
    '编辑连接…': 'Edit Connection…',
    '删除连接…': 'Delete Connection…',
    '连接属性': 'Connection Properties',
    '取消': 'Cancel',
    '保存': 'Save',
    '自动继续证书主机名不匹配提示': 'Automatically continue on certificate hostname mismatch',
    '留空则使用 IP 地址': 'Leave blank to use the IP address',
    '显示 / 隐藏密码': 'Show / hide password',
    '用户名': 'Username',
    '密码': 'Password',
    '认证 · 按服务器要求填写': 'Authentication · As required by the server',
    '高级设置': 'Advanced',
    '无法读取系统钥匙环：': 'Unable to read the system keyring: ',
    '无法保存密码：': 'Unable to save password: ',
    '无法删除钥匙环中的密码：': 'Unable to remove password from the keyring: ',
    '删除连接？': 'Delete Connection?',
    '删除“': 'Delete “',
    '”？\n此设备的已保存登录信息也会被移除。': '”?\nSaved login information for this device will also be removed.',
    '删除': 'Delete',
    '连接选项': 'Connection Options',
    '确定': 'OK',
    '打开方式': 'Window Mode',
    '普通窗口': 'Normal window',
    '最大化': 'Maximized',
    '全屏': 'Full Screen',
    '远程分辨率': 'Remote Resolution',
    '固定 1920×1080': 'Fixed 1920×1080',
    '随窗口调整': 'Resize with window',
    '保持服务器当前分辨率': 'Keep current server resolution',
    '将远程画面缩放至窗口': 'Scale remote desktop to fit window',
    '画面缩放只改变本机显示，不改变远程分辨率。': 'Scaling changes the local view, not the remote resolution.',
    '所有连接自动继续证书主机名不匹配提示': 'Automatically continue on certificate hostname mismatch for all connections',
    '控制与共享': 'Control and Sharing',
    '仅查看，不发送鼠标和键盘': 'View only; do not send mouse or keyboard input',
    '允许共享远程桌面': 'Allow sharing the remote desktop',
    '无法打开文件传输：': 'Unable to open file transfer: ',
    '用户名或密码过长。': 'The username or password is too long.',
    '正在连接': 'Connecting',
    '正在连接 ': 'Connecting to ',
    '凭据数据不完整。': 'Incomplete credential data.',
    '凭据数据无效。': 'Invalid credential data.',
    '无法保存登录信息：': 'Unable to save login information: ',
    '连接超时：': 'Connection timed out: ',
    '\n请检查 IP地址、网络和远程电脑的 VNC 服务。': '\nCheck the IP address, network and VNC service on the remote computer.',
    '连接已关闭：': 'Connection closed: ',
    '连接未完成：': 'Connection failed: ',
    'VNCMing\n简洁连接，随时访问你的设备\n基于 TigerVNC 的远程桌面客户端。\n密码保存在系统钥匙环中。': 'VNCMing\nSimple connections. Access your devices anytime.\nA remote desktop client based on TigerVNC.\nPasswords are stored in the system keyring.',
    '更多操作': 'More Actions',
    '本机': 'This Computer',
    '下载': 'Download',
    '上传': 'Upload',
    '上级目录': 'Parent Directory',
    '下级目录（返回刚才的目录）': 'Forward (return to the previous directory)',
    '刷新': 'Refresh',
    '新建文件夹…': 'New Folder…',
    '大小': 'Size',
    '修改时间': 'Modified',
    '正在读取…': 'Loading…',
    '操作失败：': 'Operation failed: ',
    '文件夹': 'Folder',
    '{count} 个项目 · 双击文件夹进入': '{count} items · Double-click a folder to open',
    '新建文件夹': 'New Folder',
    '文件夹名称': 'Folder Name',
    '创建': 'Create',
    '仅支持本机文件': 'Only local files are supported',
    '文件传输 · ': 'File Transfer · ',
    '文件传输': 'File Transfer',
    '尚未连接': 'Not connected',
    '重新连接…': 'Reconnect…',
    '连接设置': 'Connection Settings',
    '传输任务': 'Transfers',
    '重试失败任务': 'Retry Failed Transfers',
    '取消全部传输': 'Cancel All Transfers',
    '清除已结束任务': 'Clear Finished Transfers',
    '方向': 'Direction',
    '状态': 'Status',
    '进度': 'Progress',
    '大小 / 速度': 'Size / Speed',
    '暂无传输任务': 'No transfers',
    '连接文件传输': 'Connect File Transfer',
    '请填写此设备的 SSH 用户名。': 'Enter the SSH username for this device.',
    '无法读取登录信息：': 'Unable to read login information: ',
    '请先完成或取消传输任务': 'Finish or cancel transfers first',
    '主机': 'Host',
    'SSH 端口': 'SSH Port',
    'SSH 密码': 'SSH Password',
    '使用当前设备的地址': 'Use the current device address',
    '留空使用 SSH 密钥 / Agent': 'Leave blank to use an SSH key / agent',
    '将 SSH 密码保存到系统钥匙环': 'Save SSH password in the system keyring',
    '默认使用远程登录密码；SSH 密码不同时可在此修改。': 'Uses the remote login password by default. Change it here if the SSH password differs.',
    '钥匙环读取失败：': 'Unable to read keyring: ',
    '请输入主机、用户名和有效端口': 'Enter a host, username and valid port',
    '正在连接…': 'Connecting…',
    '确认远程设备身份': 'Confirm Remote Identity',
    '\n\n主机指纹\n': '\n\nHost fingerprint\n',
    '\n\n请核对后再信任此设备。': '\n\nVerify the fingerprint before trusting this device.',
    '信任并连接': 'Trust and Connect',
    '已连接 · ': 'Connected · ',
    '连接失败': 'Connection failed',
    'SSH 连接失败，请检查用户名、密码和端口。\n': 'SSH connection failed. Check the username, password and port.\n',
    '无法保存 SSH 密码': 'Unable to Save SSH Password',
    '关闭': 'Close',
    '请先连接设备并打开目标文件夹': 'Connect a device and open a destination folder first',
    '请先选择文件或文件夹': 'Select a file or folder first',
    '目标已有同名文件': 'A File Already Exists',
    '\n\n本任务后续同名文件也使用此选项。文件夹会合并。': '\n\nApply this choice to subsequent conflicts in this transfer. Folders will be merged.',
    '取消任务': 'Cancel Transfer',
    '跳过': 'Skip',
    '保留两份': 'Keep Both',
    '覆盖': 'Replace',
    '等待中': 'Waiting',
    '正在传输': 'Transferring',
    '正在取消': 'Cancelling',
    '已完成': 'Completed',
    '已取消': 'Cancelled',
    '失败': 'Failed',
    '已完成 · 跳过 {count} 项': 'Completed · {count} skipped',
    '重试': 'Retry',
    '停止传输？': 'Stop Transfers?',
    '关闭此窗口将取消未完成的传输。': 'Closing this window will cancel unfinished transfers.',
    '继续传输': 'Continue Transfers',
    '取消传输并关闭': 'Cancel Transfers and Close',
    '无效文件名称': 'Invalid file name',
    '未确认远端身份': 'Remote identity was not confirmed',
    '暂不传输符号链接：': 'Symbolic links are not supported: ',
    '目标是符号链接，无法写入：': 'Cannot write to a symbolic link: ',
    '目标不是普通文件：': 'The destination is not a regular file: ',
    '不支持特殊文件：': 'Special files are not supported: ',
    '目标已有同名文件：': 'A file already exists at the destination: ',
    '源文件在传输期间发生变化，请重试': 'The source file changed during transfer. Please retry.',
    '无法将密码保存到系统钥匙环。': 'Unable to save the password in the system keyring.',
    '语言': 'Language',
    '跟随系统': 'System Default',
    '重新打开 VNCMing 后，界面将使用所选语言。已连接的远程会话不受影响。': 'Reopen VNCMing to use the selected language. Existing remote sessions will continue.',
}
