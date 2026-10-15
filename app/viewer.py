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
import socket
import credentials

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from gi.repository import GdkX11
from motion import AnimatedDialog, animate_menu
from suggestions import AddressSuggestions

ROOT = Path(__file__).resolve().parent.parent
CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
DATA = CONFIG_HOME / 'vncming' / 'connections.json'
LEGACY_DATA = CONFIG_HOME / 'tigervnc-classic' / 'connections.json'
ENGINE = str(ROOT / 'build' / 'vncviewer' / 'vncviewer')

def action_icon(button, name, color='#a44d14'):
    svg = (ROOT / 'assets' / 'actions' / (name + '.svg')).read_text()
    loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
    loader.set_size(18, 18)
    loader.write(svg.replace('#a44d14', color).encode('utf-8'))
    loader.close()
    button.set_image(Gtk.Image.new_from_pixbuf(loader.get_pixbuf()))
    button.set_image_position(Gtk.PositionType.LEFT)
    button.set_always_show_image(True)


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
    def __init__(self, show_window=True):
        GLib.set_prgname('vncming')
        Gdk.set_program_class('VNCMing')
        super().__init__(title='VNCMing')
        self.set_default_size(900, 610)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(str(ROOT / 'assets' / 'vncming-orange.png'))
        Gtk.Window.set_default_icon_from_file(str(ROOT / 'assets' / 'vncming-orange.png'))
        self.connect('destroy', Gtk.main_quit)
        self.connect('button-press-event', self.clear_entry_focus)
        self.entries = []
        self.approved_hostname_hosts = set()
        self.options = {'FullScreen': False, 'Maximize': True, 'FixedResolution': True, 'FitToWindow': True, 'RemoteResize': False, 'ViewOnly': False, 'Shared': True}
        self.children = {}
        self.transfer_windows = {}
        self.connect('destroy', lambda *_: [w.destroy() for w in list(self.transfer_windows.values())])
        self.pending_connections = {}
        self.connect('destroy', lambda *_: [self.cancel_pending(address)
                     for address in list(self.pending_connections)])
        try:
            saved = json.loads((DATA if DATA.exists() else LEGACY_DATA).read_text())
            self.entries = [e for e in saved.get('connections', []) if isinstance(e, dict) and isinstance(e.get('address'), str) and isinstance(e.get('name'), str)]
            self.options.update({k: v for k, v in saved.get('options', {}).items() if k in self.options and isinstance(v, bool)})
            # Earlier versions opened full screen. Migrate that startup default once.
            if 'Maximize' not in saved.get('options', {}):
                self.options.update(FullScreen=False, Maximize=True)
            self.approved_hostname_hosts = {host for host in saved.get('approved_hostname_hosts', []) if isinstance(host, str)}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        if self.options['FullScreen']:
            self.options['Maximize'] = False
        if self.options['FixedResolution']:
            self.options['RemoteResize'] = False
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
        self.menu_bar = menu
        menu.get_style_context().add_class('desktop-menu')
        menu.set_valign(Gtk.Align.CENTER)
        for label, actions in [('文件', [('新建', self.new_connection), ('文件传输…', self.open_transfer), ('退出', lambda *_: self.destroy())]), ('查看', [('连接选项…', self.show_options)]), ('帮助', [('关于', self.about)])]:
            item = Gtk.MenuItem(label=label)
            sub = Gtk.Menu()
            sub.get_style_context().add_class('desktop-submenu')
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
        self.address = Gtk.Entry()
        self.address.set_tooltip_text('IP地址或主机名')
        toolbar.pack_start(Gtk.Label(label='地址'), False, False, 0)
        self.address.connect('activate', self.connect_address)
        toolbar.pack_start(self.address, True, True, 0)
        self.address.set_placeholder_text('输入地址或搜索连接')
        self.suggestions = AddressSuggestions(self.address, lambda: self.entries)
        button = Gtk.Button(label='连接')
        action_icon(button, 'connect', '#ffffff')
        button.get_style_context().add_class('connect')
        button.connect('clicked', self.connect_address)
        self.connect_button = button
        self.row_connect_buttons = []
        self.address.connect('changed', self.update_connect_actions)
        toolbar.pack_start(button, False, False, 0)
        main.pack_start(toolbar, False, False, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_border_width(24)
        main.pack_start(body, True, True, 0)
        heading = Gtk.Box(spacing=8)
        title_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        title_line = Gtk.Box(spacing=10)
        label = Gtk.Label(label='我的连接', xalign=0)
        label.get_style_context().add_class('section')
        title_line.pack_start(label, False, False, 0)
        self.connection_count = Gtk.Label()
        self.connection_count.set_valign(Gtk.Align.CENTER)
        self.connection_count.get_style_context().add_class('count-badge')
        title_line.pack_start(self.connection_count, False, False, 0)
        title_group.pack_start(title_line, False, False, 0)
        heading.pack_start(title_group, True, True, 0)
        for title, callback in [('新建', self.new_connection)]:
            b = Gtk.Button(label=title)
            b.set_valign(Gtk.Align.CENTER)
            action_icon(b, 'new')
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
        name_heading.set_size_request(220, -1)
        columns.pack_start(name_heading, False, False, 0)
        columns.pack_start(Gtk.Label(label='IP地址', xalign=0), True, True, 0)
        action_heading = Gtk.Label()
        action_heading.set_size_request(138, -1)
        columns.pack_end(action_heading, False, False, 0)
        list_panel.pack_start(columns, False, False, 0)
        self.table = Gtk.ListBox()
        self.table.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.table.set_activate_on_single_click(False)
        self.table.connect('row-activated', lambda _, row: self.connection_dialog(row.get_index()))
        self.table.connect('row-selected', self.selected_changed)
        self.table.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.table.connect('button-press-event', self.table_context_menu)
        list_panel.pack_start(self.table, True, True, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.get_style_context().add_class('connection-panel')
        scroll.add(list_panel)
        self.stack.add_named(scroll, 'list')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        empty.set_valign(Gtk.Align.CENTER)
        empty.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROOT / 'assets' / 'vncming-orange.png'), 64, 64, True)), False, False, 0)
        title = Gtk.Label(label='连接到你的电脑')
        title.get_style_context().add_class('empty-title')
        empty.pack_start(title, False, False, 0)
        caption = Gtk.Label(label='新建一个连接，或在上方输入 IP 地址直接访问')
        caption.get_style_context().add_class('muted')
        empty.pack_start(caption, False, False, 0)
        create = Gtk.Button(label='新建连接')
        action_icon(create, 'new', '#ffffff')
        create.set_halign(Gtk.Align.CENTER)
        create.get_style_context().add_class('suggested-action')
        create.connect('clicked', self.new_connection)
        empty.pack_start(create, False, False, 0)
        self.stack.add_named(empty, 'empty')
        self.status = Gtk.Label()
        if show_window:
            self.show_all()
        self.refresh()
        self.set_focus(None)

    @staticmethod
    def clear_entry_focus(window, event):
        widget = Gtk.get_event_widget(event)
        while widget is not None:
            if isinstance(widget, (Gtk.Entry, Gtk.Popover)):
                return False
            widget = widget.get_parent()
        if isinstance(window.get_focus(), Gtk.Entry):
            window.set_focus(None)
        return False

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
        self.connection_count.set_text(str(len(self.entries)))
        self.row_connect_buttons = []
        for row in self.table.get_children():
            self.table.remove(row)
        for index, entry in enumerate(self.entries):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=20, margin_start=14, margin_end=14, margin_top=8, margin_bottom=8)
            row.set_tooltip_text('双击编辑连接，或右键打开操作菜单')
            row.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            row.connect('button-press-event', self.connection_context_menu)
            name = Gtk.Label(label=entry['name'], xalign=0, ellipsize=3)
            name_column = Gtk.Box(spacing=8)
            name.get_style_context().add_class('connection-name')
            name_column.set_size_request(220, -1)
            icon = Gtk.Image.new_from_icon_name('video-display-symbolic', Gtk.IconSize.BUTTON)
            icon.get_style_context().add_class('device-icon')
            name_column.pack_start(icon, False, False, 0)
            name_column.pack_start(name, True, True, 0)
            if index == 0:
                latest = Gtk.Label(label='最近保存')
                latest.set_valign(Gtk.Align.CENTER)
                latest.set_tooltip_text('最新保存的连接')
                latest.get_style_context().add_class('latest-connection')
                name_column.pack_end(latest, False, False, 0)
            box.pack_start(name_column, False, False, 0)
            address_label = Gtk.Label(label=entry['address'], xalign=0, selectable=False, ellipsize=3)
            address_label.get_style_context().add_class('connection-address')
            address_label.set_tooltip_text(entry['address'])
            name.set_tooltip_text(entry['name'])
            box.pack_start(address_label, True, True, 0)
            button = Gtk.Button(label='连接')
            action_icon(button, 'connect')
            button.set_size_request(96, -1)
            button.get_style_context().add_class('row-connect')
            button.connect('clicked', lambda _, i=index: self.connect_entry(i))
            self.row_connect_buttons.append((entry['address'], button))
            actions = Gtk.Box(spacing=8)
            actions.pack_start(button, False, False, 0)
            delete = Gtk.Button()
            action_icon(delete, 'delete', '#8a7e72')
            delete.set_tooltip_text('删除连接：' + entry['name'])
            delete.get_accessible().set_name('删除连接：' + entry['name'])
            delete.get_style_context().add_class('row-delete')
            delete.connect('clicked', lambda _, i=index: self.delete_connection(index=i))
            actions.pack_start(delete, False, False, 0)
            box.pack_end(actions, False, False, 0)
            row.add(box)
            self.table.add(row)
        self.table.show_all()
        self.stack.set_visible_child_name('list' if self.entries else 'empty')
        self.update_connect_actions()

    def update_connect_actions(self, *_):
        try:
            address = target_address(self.address.get_text())
        except ValueError:
            address = None
        pending = address in self.pending_connections
        self.connect_button.set_label('正在连接…' if pending else '连接')
        self.connect_button.set_sensitive(address is not None and not pending)
        for target, button in self.row_connect_buttons:
            button.set_sensitive(target not in self.pending_connections)

    def table_context_menu(self, table, event):
        if event.button != 3:
            return False
        row = table.get_row_at_y(int(event.y))
        return self.connection_context_menu(row, event) if row else False

    def connection_context_menu(self, row, event):
        if event.button != 3:
            return False
        index = row.get_index()
        self.table.select_row(row)
        previous = getattr(self, 'connection_menu', None)
        if previous:
            previous.destroy()
        menu = Gtk.Menu()
        self.connection_menu = menu
        for caption, callback in [('连接', self.connect_entry), ('编辑连接…', self.connection_dialog), ('删除连接…', lambda i: self.delete_connection(index=i))]:
            item = Gtk.MenuItem(label=caption)
            item.connect('activate', lambda _, action=callback: action(index))
            menu.append(item)
        menu.attach_to_widget(row, None)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def selection(self):
        row = self.table.get_selected_row()
        return row.get_index() if row else None

    def selected_changed(self, *_):
        index = self.selection()
        if index is not None:
            self.address.set_text(self.entries[index]['address'])

    def connection_dialog(self, index=None):
        dialog = AnimatedDialog(title='连接属性' if index is not None else '新建连接', transient_for=self, modal=True)
        dialog.connect('button-press-event', self.clear_entry_focus)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        grid = Gtk.Grid(column_spacing=14, row_spacing=14, margin=20)
        allow_hostname_mismatch = Gtk.CheckButton(label='自动继续证书主机名不匹配提示')
        name, address, username, password = Gtk.Entry(), Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
        name.set_placeholder_text('留空则使用 IP 地址')
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
        for row, (caption, field) in enumerate([('名称', name), ('地址', address), ('用户名', username), ('密码', password)]):
            row += int(row >= 2)
            grid.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            grid.attach(field, 1, row, 1, 1)
        auth_title = Gtk.Label(label='认证 · 按服务器要求填写', xalign=0)
        auth_title.get_style_context().add_class('muted')
        grid.attach(auth_title, 0, 2, 2, 1)
        advanced = Gtk.Expander(label='高级设置')
        advanced.add(allow_hostname_mismatch)
        grid.attach(advanced, 0, 5, 2, 1)
        validation = Gtk.Label(xalign=0, wrap=True, max_width_chars=48)
        validation.get_style_context().add_class('validation-error')
        grid.attach(validation, 0, 6, 2, 1)
        dialog.get_content_area().add(grid)
        dialog.show_all()
        dialog.set_focus(None)
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                target = target_address(address.get_text())
            except ValueError as error:
                validation.set_text(str(error))
                address.grab_focus()
                continue
            try:
                self.save_connection(name.get_text(), target, username.get_text(), password.get_text(), index,
                                     allow_hostname_mismatch.get_active())
            except (GLib.Error, RuntimeError) as error:
                validation.set_text('无法保存密码：' + str(error))
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
            credentials.clear(old_identifier + ':sftp')
        entry = {'name': name, 'address': target, 'username': username, 'credential_id': identifier,
                 'allow_hostname_mismatch': bool(allow_hostname_mismatch)}
        if source is not None:
            entry.update({key: self.entries[source][key] for key in ('ssh_port', 'ssh_username')
                          if key in self.entries[source]})
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
            if not self.confirm_delete(self.entries[index]):
                return
            try:
                credentials.clear(self.entries[index].get("credential_id"))
                identifier = self.entries[index].get('credential_id')
                if identifier:
                    credentials.clear(identifier + ':sftp')
            except GLib.Error as error:
                self.message("无法删除钥匙环中的密码：" + str(error))
                return
            del self.entries[index]
            self.save()
            self.refresh()

    def confirm_delete(self, entry):
        dialog = AnimatedDialog(title='删除连接？', transient_for=self, modal=True)
        label = Gtk.Label(label='删除“' + entry['name'] + '”？\n此设备的已保存登录信息也会被移除。', wrap=True, max_width_chars=48, margin=24)
        dialog.get_content_area().add(label)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '删除', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('destructive-action')
        dialog.show_all()
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.hide()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def show_options(self, *_):
        dialog = AnimatedDialog(title='连接选项', transient_for=self, modal=True)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '确定', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24)
        dialog.get_content_area().add(box)
        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        box.pack_start(grid, False, False, 0)
        def selector(caption, choices, selected, row):
            field = Gtk.ComboBoxText()
            for key, label in choices:
                field.append(key, label)
            field.set_active_id(selected)
            field.set_hexpand(True)
            grid.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            grid.attach(field, 1, row, 1, 1)
            return field
        opening = selector('打开方式', [('normal', '普通窗口'), ('maximized', '最大化'), ('fullscreen', '全屏')],
                           'fullscreen' if self.options['FullScreen'] else ('maximized' if self.options['Maximize'] else 'normal'), 0)
        resolution = selector('远程分辨率', [('fixed', '固定 1920×1080'), ('dynamic', '随窗口调整'), ('server', '保持服务器当前分辨率')],
                              'fixed' if self.options['FixedResolution'] else ('dynamic' if self.options['RemoteResize'] else 'server'), 1)
        fit = Gtk.CheckButton(label='将远程画面缩放至窗口')
        fit.set_active(self.options['FitToWindow'])
        box.pack_start(fit, False, False, 0)
        note = Gtk.Label(label='画面缩放只改变本机显示，不改变远程分辨率。', xalign=0, wrap=True)
        note.get_style_context().add_class('muted')
        box.pack_start(note, False, False, 0)
        advanced = Gtk.Expander(label='控制与共享')
        advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=8)
        checks = {}
        for key, label in [('ViewOnly', '仅查看，不发送鼠标和键盘'), ('Shared', '允许共享远程桌面')]:
            checks[key] = Gtk.CheckButton(label=label)
            checks[key].set_active(self.options[key])
            advanced_box.pack_start(checks[key], False, False, 0)
        advanced.add(advanced_box)
        box.pack_start(advanced, False, False, 0)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            mode, size = opening.get_active_id(), resolution.get_active_id()
            self.options.update(FullScreen=mode == 'fullscreen', Maximize=mode == 'maximized',
                                FixedResolution=size == 'fixed', RemoteResize=size == 'dynamic', FitToWindow=fit.get_active(),
                                **{key: check.get_active() for key, check in checks.items()})
            self.save()
        dialog.destroy()

    def connect_entry(self, index):
        if 0 <= index < len(self.entries):
            self.start_connection(self.entries[index]['address'], self.entries[index])

    def open_transfer(self, *_, index=None):
        try:
            from file_transfer import TransferWindow
            if index is None:
                index = self.selection()
            if index is not None:
                entry = self.entries[index]
            else:
                address = target_address(self.address.get_text())
                entry = next((e for e in self.entries if e['address'] == address),
                             {'name': address, 'address': address})
            key = (entry['address'], entry.get('username', ''))
            if key in self.transfer_windows:
                self.transfer_windows[key].present()
                return
            window = TransferWindow(self, entry)
            self.transfer_windows[key] = window
            window.connect('destroy', lambda *_: self.transfer_windows.pop(key, None))
            GLib.idle_add(window.auto_connect)
        except (ValueError, ImportError) as error:
            self.message('无法打开文件传输：' + str(error))

    def connect_address(self, *_):
        self.suggestions.popup.popdown()
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
        save_reader = save_writer = None
        try:
            address = target_address(address)
            if address in self.pending_connections:
                self.pending_connections[address]['dialog'].present()
                return
            args = [ENGINE] + ['-' + key + '=' + str(int(value)) for key, value in self.options.items() if key != 'FixedResolution']
            if self.options['FixedResolution']:
                args.append('-DesktopSize=1920x1080')
            else:
                args.append('-FullScreenDesktopSize=')
            args.append(address)
            environment = os.environ.copy()
            environment.pop('VNCMING_PARENT_WINDOW', None)
            parent_window = self.get_window()
            if isinstance(parent_window, GdkX11.X11Window):
                environment['VNCMING_PARENT_WINDOW'] = str(parent_window.get_xid())
            environment['VNCMING_TRANSFER_LAUNCHER'] = str(ROOT / 'vncming')
            environment['VNCMING_TRANSFER_ADDRESS'] = address
            environment['VNCMING_TRANSFER_CONNECTION_ID'] = entry.get('credential_id', '') if entry else ''
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
            save_reader, save_writer = socket.socketpair(type=socket.SOCK_DGRAM)
            save_reader.setblocking(False)
            environment['VNCMING_SAVE_CREDENTIALS_FD'] = str(save_writer.fileno())
            inherited += (save_writer.fileno(),)
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
            if save_reader is not None:
                save_reader.close()
            self.message(str(error))
            return
        finally:
            if save_writer is not None:
                save_writer.close()
            for descriptor in (read_fd, write_fd, ready_write):
                if descriptor is not None:
                    os.close(descriptor)
        self.children[process.pid] = process
        GLib.timeout_add(100, self.poll_saved_credentials, process, save_reader, address,
                         entry.get("credential_id") if entry else None)
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
        self.update_connect_actions()
        GLib.timeout_add(100, self.poll_pending, address)
        GLib.timeout_add(500, self.poll_child, process, address)

    def poll_saved_credentials(self, process, channel, address, identifier):
        try:
            packet = channel.recv(8201)
        except BlockingIOError:
            if process.poll() is None:
                return True
            channel.close()
            return False
        except OSError:
            channel.close()
            return False
        channel.close()
        if packet == b"\0":
            return False
        try:
            if len(packet) < 8:
                raise ValueError('凭据数据不完整。')
            user_length, pass_length = struct.unpack('!II', packet[:8])
            if user_length > 4096 or not 0 < pass_length <= 4096 or len(packet) != 8 + user_length + pass_length:
                raise ValueError('凭据数据无效。')
            username = packet[8:8 + user_length].decode('utf-8')
            password = packet[8 + user_length:].decode('utf-8')
            # Resolve by stable ID: rows may have moved while authentication was open.
            index = next((i for i, e in enumerate(self.entries)
                          if identifier and e.get('credential_id') == identifier and e['address'] == address), None)
            if identifier and index is None:
                return False  # A device deleted during login must stay deleted.
            old = self.entries[index] if index is not None else None
            username = username or (old.get('username', '') if old else '')
            self.save_connection(old['name'] if old else address, address, username, password, index)
        except (ValueError, UnicodeError, GLib.Error, RuntimeError) as error:
            self.message('无法保存登录信息：' + str(error))
        return False

    def finish_pending(self, address):
        pending = self.pending_connections.pop(address, None)
        if pending:
            os.close(pending['descriptor'])
            pending['dialog'].hide()
            pending['dialog'].destroy()
            self.update_connect_actions()
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
        if ready in (b'1', b'0', b'') or pending['process'].poll() is not None:
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
    if '--files' in sys.argv:
        index = sys.argv.index('--files')
        address = target_address(sys.argv[index + 1])
        launcher = Viewer(show_window=False)
        launcher.address.set_text(address)
        connection_id = os.environ.get('VNCMING_TRANSFER_CONNECTION_ID')
        saved_index = next((i for i, e in enumerate(launcher.entries)
                            if connection_id and e.get('credential_id') == connection_id and e['address'] == address), None)
        launcher.open_transfer(index=saved_index)
        for window in launcher.transfer_windows.values():
            window.connect('destroy', lambda *_: launcher.destroy())
        if launcher.transfer_windows:
            Gtk.main()
    elif '--theme-check' in sys.argv:
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
