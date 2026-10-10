#!/usr/bin/python3
"""Classic desktop launcher for the system TigerVNC viewer."""
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import struct
import credentials

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from motion import AnimatedDialog, animate_menu

ROOT = Path(__file__).resolve().parent.parent
CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
DATA = CONFIG_HOME / 'vncming' / 'connections.json'
LEGACY_DATA = CONFIG_HOME / 'tigervnc-classic' / 'connections.json'
ENGINE = str(ROOT / 'build' / 'vncviewer' / 'vncviewer')


def target_address(value):
    value = value.strip()
    if value.startswith('vnc://'):
        value = value[6:].rstrip('/')
        # URI ports denote TCP ports; TigerVNC single-colon ports denote displays.
        m = re.fullmatch(r'([^:]+):(\d+)', value)
        if m:
            value = m[1] + '::' + m[2]
    m = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[a-zA-Z0-9][a-zA-Z0-9._-]*)(?:(::?)(\d+))?', value)
    if not m:
        raise ValueError('请输入 IP 或主机名，例如 192.168.1.100；指定端口用 192.168.1.100::5901。')
    host, separator, number = m.groups()
    if host.startswith('['):
        ipaddress.IPv6Address(host[1:-1])
    elif re.fullmatch(r'[0-9.]+', host):
        ipaddress.IPv4Address(host)
    if number is not None:
        maximum = 65535 if separator == '::' else 59635
        if not 0 <= int(number) <= maximum or (separator == '::' and int(number) == 0):
            raise ValueError('端口或显示编号超出有效范围。')
    return value


class Viewer(Gtk.Window):
    def __init__(self):
        GLib.set_prgname('vncming')
        Gdk.set_program_class('VNCMing')
        super().__init__(title='VNCMing')
        self.set_default_size(900, 610)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(str(ROOT / 'assets' / 'vncming-orange.png'))
        Gtk.Window.set_default_icon_from_file(str(ROOT / 'assets' / 'vncming-orange.png'))
        self.connect('destroy', Gtk.main_quit)
        self.entries = []
        self.approved_hostname_hosts = set()
        self.options = {'FullScreen': True, 'FitToWindow': True, 'RemoteResize': True, 'ViewOnly': False, 'Shared': True}
        self.children = {}
        self.pending_connections = {}
        self.connect('destroy', lambda *_: [self.cancel_pending(address)
                     for address in list(self.pending_connections)])
        try:
            saved = json.loads((DATA if DATA.exists() else LEGACY_DATA).read_text())
            self.entries = [e for e in saved.get('connections', []) if isinstance(e, dict) and isinstance(e.get('address'), str) and isinstance(e.get('name'), str)]
            self.options.update({k: v for k, v in saved.get('options', {}).items() if k in self.options and isinstance(v, bool)})
            self.approved_hostname_hosts = {host for host in saved.get('approved_hostname_hosts', []) if isinstance(host, str)}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        css = Gtk.CssProvider()
        css.load_from_path(str(ROOT / 'app' / 'theme.css'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        header = Gtk.HeaderBar()
        header.set_title('VNCMing')
        header.set_show_close_button(True)
        header.set_decoration_layout(':minimize,maximize,close')
        header.set_has_subtitle(False)
        self.set_titlebar(header)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main)
        menu = Gtk.MenuBar()
        for label, actions in [('文件', [('新建', self.new_connection), ('退出', lambda *_: self.destroy())]), ('查看', [('连接选项…', self.show_options)]), ('帮助', [('关于', self.about)])]:
            item = Gtk.MenuItem(label=label)
            sub = Gtk.Menu()
            animate_menu(sub)
            for name, callback in actions:
                action = Gtk.MenuItem(label=name)
                action.connect('activate', callback)
                sub.append(action)
            item.set_submenu(sub)
            menu.append(item)
        main.pack_start(menu, False, False, 0)
        toolbar = Gtk.Box(spacing=10)
        toolbar.get_style_context().add_class('toolbar')
        toolbar.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'assets' / 'vncming-orange.png'), 32, 32, True)), False, False, 0)
        self.address = Gtk.Entry()
        self.address.set_tooltip_text('IP地址或主机名')
        toolbar.pack_start(Gtk.Label(label='IP地址'), False, False, 0)
        self.address.connect('activate', self.connect_address)
        toolbar.pack_start(self.address, True, True, 0)
        button = Gtk.Button(label='连接')
        button.get_style_context().add_class('connect')
        button.connect('clicked', self.connect_address)
        toolbar.pack_start(button, False, False, 0)
        main.pack_start(toolbar, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_border_width(24)
        main.pack_start(body, True, True, 0)
        heading = Gtk.Box(spacing=8)
        label = Gtk.Label(label='我的连接', xalign=0)
        label.get_style_context().add_class('section')
        heading.pack_start(label, True, True, 0)
        for title, callback in [('新建', self.new_connection)]:
            b = Gtk.Button(label=title)
            b.connect('clicked', callback)
            heading.pack_start(b, False, False, 0)
        body.pack_start(heading, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(220)
        body.pack_start(self.stack, True, True, 0)
        list_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        columns = Gtk.Box(spacing=20, margin_start=14, margin_end=14, margin_top=8, margin_bottom=8)
        columns.get_style_context().add_class('list-columns')
        name_heading = Gtk.Label(label='名称', xalign=0)
        name_heading.set_size_request(200, -1)
        columns.pack_start(name_heading, False, False, 0)
        columns.pack_start(Gtk.Label(label='IP地址', xalign=0), True, True, 0)
        action_heading = Gtk.Label(label='操作')
        action_heading.set_size_request(168, -1)
        columns.pack_end(action_heading, False, False, 0)
        list_panel.pack_start(columns, False, False, 0)
        self.table = Gtk.ListBox()
        self.table.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.table.set_activate_on_single_click(False)
        self.table.connect('row-activated', lambda _, row: self.connection_dialog(row.get_index()))
        self.table.connect('row-selected', self.selected_changed)
        list_panel.pack_start(self.table, True, True, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.add(list_panel)
        self.stack.add_named(scroll, 'list')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        empty.set_valign(Gtk.Align.CENTER)
        empty.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'assets' / 'vncming-orange.png'), 64, 64, True)), False, False, 0)
        title = Gtk.Label(label='连接到你的电脑')
        title.get_style_context().add_class('empty-title')
        empty.pack_start(title, False, False, 0)
        self.stack.add_named(empty, 'empty')
        self.status = Gtk.Label()
        self.show_all()
        self.refresh()
        self.address.grab_focus()

    def message(self, text):
        dialog = AnimatedDialog(title='VNCMing', transient_for=self, modal=True)
        dialog.add_button('好', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24)
        image = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'assets' / 'vncming-orange.png'), 56, 56, True))
        box.pack_start(image, False, False, 0)
        label = Gtk.Label(label=text, wrap=True, max_width_chars=44, selectable=True)
        label.set_justify(Gtk.Justification.CENTER)
        label.get_style_context().add_class('message-body')
        box.pack_start(label, False, False, 0)
        dialog.get_content_area().add(box)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def save(self):
        try:
            DATA.parent.mkdir(parents=True, exist_ok=True)
            temporary = DATA.with_suffix('.tmp')
            temporary.write_text(json.dumps({'connections': self.entries, 'options': self.options,
                'approved_hostname_hosts': sorted(self.approved_hostname_hosts)}, ensure_ascii=False, indent=2))
            temporary.replace(DATA)
        except OSError as error:
            self.message('无法保存连接：' + str(error))

    def refresh(self):
        for row in self.table.get_children():
            self.table.remove(row)
        for index, entry in enumerate(self.entries):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=20, margin=14)
            name = Gtk.Label(label=entry['name'], xalign=0, ellipsize=3)
            name_column = Gtk.Box(spacing=8)
            name_column.set_size_request(200, -1)
            name_column.pack_start(name, True, True, 0)
            if index == 0:
                latest = Gtk.Label(label='★')
                latest.set_tooltip_text('最新保存的连接')
                latest.get_style_context().add_class('latest-connection')
                name_column.pack_end(latest, False, False, 0)
            box.pack_start(name_column, False, False, 0)
            box.pack_start(Gtk.Label(label=entry['address'], xalign=0, selectable=False), True, True, 0)
            button = Gtk.Button(label='连接')
            button.set_size_request(80, -1)
            button.get_style_context().add_class('row-connect')
            button.connect('clicked', lambda _, i=index: self.connect_entry(i))
            actions = Gtk.Box(spacing=8)
            actions.pack_start(button, False, False, 0)
            delete = Gtk.Button(label='删除')
            delete.set_size_request(80, -1)
            delete.get_style_context().add_class('row-delete')
            delete.connect('clicked', lambda _, i=index: self.delete_connection(index=i))
            actions.pack_start(delete, False, False, 0)
            box.pack_end(actions, False, False, 0)
            row.add(box)
            self.table.add(row)
        self.table.show_all()
        self.stack.set_visible_child_name('list' if self.entries else 'empty')

    def selection(self):
        row = self.table.get_selected_row()
        return row.get_index() if row else None

    def selected_changed(self, *_):
        index = self.selection()
        if index is not None:
            self.address.set_text(self.entries[index]['address'])

    def connection_dialog(self, index=None):
        dialog = AnimatedDialog(title='连接属性' if index is not None else '新建', transient_for=self, modal=True)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        grid = Gtk.Grid(column_spacing=14, row_spacing=14, margin=20)
        allow_hostname_mismatch = Gtk.CheckButton(label='自动继续证书主机名不匹配提示')
        name, address, username, password = Gtk.Entry(), Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
        password.set_visibility(False)
        password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        password.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")
        password.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "显示 / 隐藏密码")
        password.connect("icon-press", lambda entry, *_: entry.set_visibility(not entry.get_visibility()))
        address.set_width_chars(38)
        if index is not None:
            name.set_text(self.entries[index]['name'])
            address.set_text(self.entries[index]['address'])
            username.set_text(self.entries[index].get('username', ''))
            host = self.entries[index]['address'].split(']')[0].lstrip('[') if self.entries[index]['address'].startswith('[') else self.entries[index]['address'].split(':', 1)[0]
            allow_hostname_mismatch.set_active(self.entries[index].get('allow_hostname_mismatch', host in self.approved_hostname_hosts))
            try:
                password.set_text(credentials.lookup(self.entries[index].get('credential_id')))
            except (GLib.Error, RuntimeError) as error:
                self.message('无法读取系统钥匙环：' + str(error))
                dialog.destroy()
                return
        else:
            address.set_text(self.address.get_text())
            host = address.get_text().split(']')[0].lstrip('[') if address.get_text().startswith('[') else address.get_text().split(':', 1)[0]
            allow_hostname_mismatch.set_active(host in self.approved_hostname_hosts)
        for row, (caption, field) in enumerate([('名称', name), ('IP地址', address), ('用户名', username), ('密码', password)]):
            grid.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            grid.attach(field, 1, row, 1, 1)
        grid.attach(allow_hostname_mismatch, 0, 4, 2, 1)
        dialog.get_content_area().add(grid)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                target = target_address(address.get_text())
            except ValueError as error:
                self.message(str(error))
                continue
            try:
                self.save_connection(name.get_text(), target, username.get_text(), password.get_text(), index,
                                     allow_hostname_mismatch.get_active())
            except (GLib.Error, RuntimeError) as error:
                self.message('无法保存密码：' + str(error))
                continue
            break
        dialog.destroy()

    def save_connection(self, name, address, username, password, index=None, allow_hostname_mismatch=None):
        target = target_address(address)
        username = username.strip()
        matches = [i for i, existing in enumerate(self.entries)
                   if existing['address'] == target and existing.get('username', '').strip() == username]
        replaced = set(matches)
        if index is not None:
            replaced.add(index)
        source = matches[0] if matches else index
        if allow_hostname_mismatch is None:
            allow_hostname_mismatch = self.entries[source].get('allow_hostname_mismatch', False) if source is not None else False
        identifier = self.entries[source].get('credential_id') if source is not None else None
        identifier = identifier or str(uuid.uuid4())
        name = name.strip() or target
        credentials.store(identifier, name, password)
        old_identifiers = {self.entries[i].get('credential_id') for i in replaced}
        for old_identifier in old_identifiers - {None, identifier}:
            credentials.clear(old_identifier)
        entry = {'name': name, 'address': target, 'username': username, 'credential_id': identifier,
                 'allow_hostname_mismatch': bool(allow_hostname_mismatch)}
        self.entries = [entry] + [existing for i, existing in enumerate(self.entries) if i not in replaced]
        self.save()
        self.refresh()
        self.table.select_row(self.table.get_row_at_index(0))

    def new_connection(self, *_):
        self.connection_dialog()

    def edit_connection(self, *_):
        index = self.selection()
        if index is not None:
            self.connection_dialog(index)

    def delete_connection(self, *_, index=None):
        if index is None:
            index = self.selection()
        if index is not None and 0 <= index < len(self.entries):
            try:
                credentials.clear(self.entries[index].get("credential_id"))
            except GLib.Error as error:
                self.message("无法删除钥匙环中的密码：" + str(error))
                return
            del self.entries[index]
            self.save()
            self.refresh()

    def show_options(self, *_):
        dialog = AnimatedDialog(title='连接选项', transient_for=self, modal=True)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '确定', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        box = dialog.get_content_area()
        box.set_border_width(18)
        checks = {}
        for key, label in [('FullScreen', '以全屏模式打开'), ('FitToWindow', '远程画面铺满窗口'), ('RemoteResize', '远程分辨率随窗口调整'), ('ViewOnly', '仅查看（不发送鼠标和键盘）'), ('Shared', '允许共享远程桌面')]:
            checks[key] = Gtk.CheckButton(label=label)
            checks[key].set_active(self.options[key])
            box.pack_start(checks[key], False, False, 7)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            self.options = {key: check.get_active() for key, check in checks.items()}
            self.save()
        dialog.destroy()

    def connect_entry(self, index):
        if 0 <= index < len(self.entries):
            self.start_connection(self.entries[index]['address'], self.entries[index])

    def connect_address(self, *_):
        try:
            address = target_address(self.address.get_text())
        except ValueError as error:
            self.message(str(error))
            return
        entry = next((e for e in self.entries if e['address'] == address), None)
        self.start_connection(address, entry)

    def start_connection(self, address, entry=None):
        read_fd = write_fd = None
        ready_read = ready_write = None
        try:
            address = target_address(address)
            if address in self.pending_connections:
                self.pending_connections[address]['dialog'].present()
                return
            args = [ENGINE] + ['-' + key + '=' + str(int(value)) for key, value in self.options.items()] + [address]
            environment = os.environ.copy()
            environment['XMODIFIERS'] = '@im=none'
            environment.pop('VNC_PASSWORD', None)
            environment.pop('VNC_USERNAME', None)
            environment.pop('VNCMING_APPROVED_HOSTNAME', None)
            environment['VNCMING_ICON'] = str(ROOT / 'assets' / 'vncming-orange.png')
            host = address.split(']', 1)[0][1:] if address.startswith('[') else address.split(':', 1)[0]
            approved = entry.get('allow_hostname_mismatch', host in self.approved_hostname_hosts) if entry else host in self.approved_hostname_hosts
            if approved:
                environment['VNCMING_APPROVED_HOSTNAME'] = host
            saved_password = credentials.lookup(entry.get('credential_id')) if entry else ''
            inherited = ()
            if saved_password:
                username = entry.get('username', '').encode('utf-8')
                secret = saved_password.encode('utf-8')
                if len(username) > 4096 or len(secret) > 4096:
                    raise ValueError('用户名或密码过长。')
                read_fd, write_fd = os.pipe()
                environment['VNCMING_CREDENTIALS_FD'] = str(read_fd)
                inherited = (read_fd,)
            ready_read, ready_write = os.pipe()
            os.set_blocking(ready_read, False)
            environment['VNCMING_STATUS_FD'] = str(ready_write)
            inherited += (ready_write,)
            process = subprocess.Popen(args, env=environment, pass_fds=inherited,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if write_fd is not None:
                os.close(read_fd)
                read_fd = None
                payload = struct.pack('!II', len(username), len(secret)) + username + secret
                while payload:
                    written = os.write(write_fd, payload)
                    payload = payload[written:]
        except (ValueError, OSError, GLib.Error, RuntimeError) as error:
            if ready_read is not None:
                os.close(ready_read)
            self.message(str(error))
            return
        finally:
            for descriptor in (read_fd, write_fd, ready_write):
                if descriptor is not None:
                    os.close(descriptor)
        self.children[process.pid] = process
        dialog = AnimatedDialog(title='正在连接', transient_for=self, modal=False)
        dialog.add_button('取消', Gtk.ResponseType.CANCEL)
        box = Gtk.Box(spacing=14, margin=24)
        spinner = Gtk.Spinner()
        spinner.start()
        box.pack_start(spinner, False, False, 0)
        box.pack_start(Gtk.Label(label='正在连接 ' + address), False, False, 0)
        dialog.get_content_area().add(box)
        self.pending_connections[address] = {'process': process, 'dialog': dialog,
            'descriptor': ready_read, 'started': GLib.get_monotonic_time()}
        dialog.connect('response', lambda *_: self.cancel_pending(address))
        dialog.show_all()
        GLib.timeout_add(100, self.poll_pending, address)
        GLib.timeout_add(500, self.poll_child, process, address)

    def finish_pending(self, address):
        pending = self.pending_connections.pop(address, None)
        if pending:
            os.close(pending['descriptor'])
            pending['dialog'].destroy()
        return pending

    def cancel_pending(self, address):
        pending = self.finish_pending(address)
        if pending and pending['process'].poll() is None:
            pending['process'].terminate()

    def poll_pending(self, address):
        pending = self.pending_connections.get(address)
        if not pending:
            return False
        try:
            ready = os.read(pending['descriptor'], 1)
        except BlockingIOError:
            ready = None
        if ready == b'1' or ready == b'' or pending['process'].poll() is not None:
            self.finish_pending(address)
            return False
        if GLib.get_monotonic_time() - pending['started'] >= 10000000:
            self.cancel_pending(address)
            self.message('连接超时：' + address + '\n请检查 IP地址、网络和远程电脑的 VNC 服务。')
            return False
        return True

    def poll_child(self, process, address):
        code = process.poll()
        if code is None:
            return True
        self.children.pop(process.pid, None)
        self.status.set_text(('连接已关闭：' if code == 0 else '连接未完成：') + address)
        return False

    def about(self, *_):
        self.message('VNCMing\n简洁连接，随时访问你的设备\n基于 TigerVNC 的远程桌面客户端。\n密码保存在系统钥匙环中。')


if __name__ == '__main__':
    if '--theme-check' in sys.argv:
        sys.path.insert(0, str(ROOT / 'tests'))
        from verify_frontend import check
        check(Viewer)
    elif '--validate' in sys.argv:
        for value, expected in [('192.168.1.100', '192.168.1.100'), ('pi.local:1', 'pi.local:1'), ('vnc://pi.local:5901', 'pi.local::5901'), ('[::1]::5900', '[::1]::5900')]:
            assert target_address(value) == expected
        for value in ['-listen', 'pi.local;touch /tmp/no', '999.0.0.1', 'pi.local::99999', 'pi.local::0']:
            try:
                target_address(value)
            except ValueError:
                pass
            else:
                raise AssertionError(value)
        print('Address validation passed')
    else:
        Viewer()
        Gtk.main()
