"""Ubuntu-style two-pane SFTP browser and asynchronous transfer queue."""
import os
from functools import lru_cache
import queue
import stat
import threading
import time
from pathlib import Path
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import credentials
from motion import AnimatedDialog
from file_transport import RemoteFiles, LocalFiles, Cancelled, connect, ssh_host, safe_name, transfer

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_TASKS = ('等待中', '正在传输', '正在取消')


@lru_cache(maxsize=64)
def icon_pixbuf(name, size=20):
    path = ROOT / 'assets/transfer' / (name + '.svg')
    if not path.exists():
        path = ROOT / 'assets/actions' / (name + '.svg')
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)


def icon(name, size=20):
    return Gtk.Image.new_from_pixbuf(icon_pixbuf(name, size))


def button(label, symbol, callback):
    widget = Gtk.Button(label=label)
    widget.set_image(icon(symbol, 18))
    widget.set_always_show_image(True)
    widget.connect('clicked', callback)
    return widget

def action_menu(items):
    widget = Gtk.MenuButton()
    widget.set_image(icon('more', 18))
    widget.set_tooltip_text('更多操作')
    widget.get_style_context().add_class('path-action')
    popover = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin=6)
    actions = {}
    for caption, callback in items:
        item = Gtk.ModelButton(text=caption)
        def activate(_, action=callback):
            popover.popdown()
            action()
        item.connect('clicked', activate)
        box.pack_start(item, False, False, 0)
        actions[caption] = item
    popover.add(box)
    box.show_all()
    widget.set_popover(popover)
    return widget, actions

class TaskActionRenderer(Gtk.CellRendererText):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.set_property('mode', Gtk.CellRendererMode.ACTIVATABLE)
        self.set_property('foreground', '#a44d14')

    def do_activate(self, event, widget, path, background_area, cell_area, flags):
        self.owner.task_action(Gtk.TreePath.new_from_string(path))
        return True


def human_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


class Browser(Gtk.Box):
    def __init__(self, owner, remote):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.owner, self.remote, self.path, self.generation = owner, remote, None, 0
        self.loading = False
        self.operations = queue.Queue()
        self.worker_thread = threading.Thread(target=self.worker, name="vncming-browse-" + str(remote))
        self.worker_thread.start()
        heading = Gtk.Box(spacing=8)
        heading.pack_start(icon('server' if remote else 'monitor'), False, False, 0)
        name = Gtk.Label(label=owner.entry.get('name', '') if remote else '本机', xalign=0, ellipsize=3)
        name.get_style_context().add_class('group-title')
        heading.pack_start(name, True, True, 0)
        tag = Gtk.Label(label=ssh_host(owner.entry['address']) if remote else '')
        tag.get_style_context().add_class('muted')
        heading.pack_end(tag, False, False, 0)
        self.transfer_button = button('下载' if remote else '上传', 'download' if remote else 'upload',
                                      lambda *_: owner.enqueue(self.selected(), not remote))
        self.transfer_button.set_sensitive(False)
        heading.pack_end(self.transfer_button, False, False, 0)
        self.pack_start(heading, False, False, 0)
        tools = Gtk.Box(spacing=6)
        self.location = Gtk.Entry()
        self.location.set_hexpand(True)
        self.location.connect('activate', lambda field: self.load(field.get_text()))
        tools.pack_start(self.location, True, True, 0)
        self.path_buttons = []
        for label, symbol, callback in [('上级目录', 'arrow-up', self.parent), ('刷新', 'refresh-cw', self.refresh)]:
            b = button('', symbol, callback)
            b.set_tooltip_text(label)
            b.get_style_context().add_class('path-action')
            tools.pack_start(b, False, False, 0)
            self.path_buttons.append(b)
        more, self.menu_actions = action_menu([('新建文件夹…', self.new_folder)])
        tools.pack_start(more, False, False, 0)
        self.pack_start(tools, False, False, 0)
        self.model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, bool)
        self.view = Gtk.TreeView(model=self.model)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.view.get_selection().connect('changed', lambda *_: owner.update_transfer_actions())
        column = Gtk.TreeViewColumn('名称')
        image = Gtk.CellRendererPixbuf()
        text = Gtk.CellRendererText(ellipsize=3)
        column.pack_start(image, False)
        column.add_attribute(image, 'pixbuf', 0)
        column.pack_start(text, True)
        column.add_attribute(text, 'text', 1)
        column.set_expand(True)
        column.set_min_width(130)
        self.view.append_column(column)
        for title, index in [('大小', 2), ('修改时间', 3)]:
            self.view.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        self.connect('size-allocate', lambda _, area: self.view.get_column(2).set_visible(area.width >= 440))
        self.view.connect('row-activated', self.open_row)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.view)
        self.pack_start(scroll, True, True, 0)
        self.note = Gtk.Label(xalign=0, ellipsize=3)
        self.note.get_style_context().add_class('muted')
        self.pack_start(self.note, False, False, 0)
        if remote:
            self.view.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
            self.view.drag_dest_add_uri_targets()
            self.view.connect('drag-data-received', self.drop_files)
            self.set_sensitive(False)
        self.update_path_actions()

    def update_path_actions(self):
        files = self.owner.remote if self.remote else LocalFiles()
        self.path_buttons[0].set_sensitive(bool(self.path and files and files.parent(self.path) != self.path))
        self.path_buttons[1].set_sensitive(bool(self.path))
        self.menu_actions['新建文件夹…'].set_sensitive(bool(self.path))

    def worker(self):
        while True:
            operation = self.operations.get()
            if operation is None:
                return
            if not self.owner.closed:
                operation()

    def files(self):
        return self.owner.browse_remote if self.remote else LocalFiles()

    def load(self, path, canonical=False):
        if self.owner.closed:
            return
        self.generation += 1
        generation = self.generation
        files = self.files()
        self.loading = True
        self.view.set_sensitive(False)
        self.note.set_text('正在读取…')
        self.menu_actions['新建文件夹…'].set_sensitive(False)
        self.owner.update_transfer_actions()
        def current():
            return not self.owner.closed and generation == self.generation
        def failed(message):
            if current():
                self.loading = False
                self.view.set_sensitive(True)
                self.note.set_text('操作失败：' + message)
                self.update_path_actions()
                self.owner.update_transfer_actions()
        def read():
            if not current():
                return
            try:
                normalized = path if canonical else files.normalize(path)
                items = sorted(files.listing(normalized), key=lambda item: (not stat.S_ISDIR(item[1].st_mode), item[0].casefold()))
                rows = []
                for name, info in items:
                    safe_name(name)
                    directory = stat.S_ISDIR(info.st_mode)
                    rows.append((name, directory, '文件夹' if directory else human_size(info.st_size),
                        time.strftime('%Y-%m-%d %H:%M', time.localtime(info.st_mtime)), files.join(normalized, name)))
            except Exception as error:
                GLib.idle_add(failed, str(error))
                return
            def show():
                if not current():
                    return False
                model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, bool)
                iterator = iter(rows)
                def append_batch():
                    if not current():
                        return False
                    for _ in range(100):
                        row = next(iterator, None)
                        if row is None:
                            self.model = model
                            self.view.set_model(model)
                            self.path = normalized
                            self.location.set_text(normalized)
                            self.loading = False
                            self.view.set_sensitive(True)
                            self.note.set_text(f'{len(items)} 个项目 · 双击文件夹进入')
                            self.update_path_actions()
                            self.owner.update_transfer_actions()
                            return False
                        name, directory, size, modified, fullpath = row
                        model.append([icon_pixbuf('folder' if directory else 'file'), name, size, modified, fullpath, directory])
                    return True
                GLib.idle_add(append_batch)
                return False
            GLib.idle_add(show)
        self.operations.put(read)

    def refresh(self, *_):
        if self.path:
            self.load(self.path, canonical=True)

    def parent(self, *_):
        if self.path:
            files = self.owner.remote if self.remote else LocalFiles()
            self.load(files.parent(self.path) or '/', canonical=True)

    def open_row(self, _, path, column):
        if self.model[path][5]:
            self.load(self.model[path][4], canonical=True)

    def selected(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [model[path][4] for path in paths]

    def new_folder(self, *_):
        if not self.path or self.loading:
            return
        dialog = AnimatedDialog(title='新建文件夹', transient_for=self.owner, modal=True)
        field = Gtk.Entry(margin=20)
        field.set_placeholder_text('文件夹名称')
        dialog.get_content_area().add(field)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '创建', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                name = safe_name(field.get_text().strip())
                files = self.files()
                target = files.join(self.path, name)
                generation = self.generation
                def create():
                    try:
                        files.mkdir(target)
                        GLib.idle_add(self.refresh)
                    except Exception as error:
                        def failed(message=str(error)):
                            if not self.owner.closed and generation == self.generation:
                                self.note.set_text('操作失败：' + message)
                        GLib.idle_add(failed)
                self.operations.put(create)
            except ValueError as error:
                self.note.set_text(str(error))
        dialog.destroy()

    def drop_files(self, widget, context, x, y, selection, info, timestamp):
        paths = []
        for uri in selection.get_uris() or []:
            try:
                path, host = GLib.filename_from_uri(uri)
                if host not in (None, '', 'localhost'):
                    raise ValueError('仅支持本机文件')
                paths.append(path)
            except (GLib.Error, ValueError):
                Gtk.drag_finish(context, False, False, timestamp)
                return
        accepted = bool(paths and self.path and self.owner.remote and not self.loading)
        if accepted:
            self.owner.enqueue(paths, True)
        Gtk.drag_finish(context, accepted, False, timestamp)


class TransferWindow(Gtk.Window):
    def __init__(self, parent, entry):
        super().__init__(title='文件传输 · ' + entry.get('name', entry['address']))
        self.entry = entry
        self.set_transient_for(parent)
        self.set_default_size(1080, 740)
        self.set_icon_from_file(str(ROOT / 'assets/vncming-orange.png'))
        self.get_style_context().add_class('transfer-window')
        self.closed = False
        self.connecting = False
        self.remote = self.client = self.browse_remote = None
        self.operations = queue.Queue()
        self.tasks = []
        self.waiters = []
        self.connect('delete-event', self.close_requested)
        self.connect('destroy', self.shutdown)
        header = Gtk.HeaderBar(title='文件传输', show_close_button=True)
        self.state = Gtk.Label(label='尚未连接')
        self.state.get_style_context().add_class('muted')
        header.pack_start(self.state)
        self.login_button = button('连接', 'server', self.login)
        self.login_button.set_no_show_all(True)
        header.pack_end(self.login_button)
        self.connection_more, self.connection_actions = action_menu([('重新连接…', self.login)])
        self.connection_more.set_no_show_all(True)
        header.pack_end(self.connection_more)
        self.set_titlebar(header)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=20)
        self.add(main)
        self.local, self.other = Browser(self, False), Browser(self, True)
        self.upload, self.download = self.local.transfer_button, self.other.transfer_button
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_wide_handle(True)
        split.pack1(self.local, True, False)
        split.pack2(self.other, True, False)
        split.set_position(510)
        main.pack_start(split, True, True, 0)
        heading = Gtk.Box(spacing=8)
        self.task_title = Gtk.Label(label='传输任务', xalign=0)
        self.task_title.get_style_context().add_class('group-title')
        heading.pack_start(self.task_title, True, True, 0)
        more, self.task_actions = action_menu([('重试失败任务', self.retry), ('取消全部传输', self.cancel_all), ('清除已结束任务', self.clear_finished)])
        heading.pack_end(more, False, False, 0)
        main.pack_start(heading, False, False, 0)
        self.task_model = Gtk.ListStore(str, str, str, int, str, str, object, str)
        self.task_view = Gtk.TreeView(model=self.task_model)
        self.task_view.set_tooltip_column(5)
        self.task_view.connect('key-press-event', self.task_key_press)
        for title, index in [('名称', 0), ('方向', 1), ('状态', 2)]:
            cell = Gtk.CellRendererText(ellipsize=3)
            column = Gtk.TreeViewColumn(title, cell, text=index)
            column.set_expand(index == 0)
            column.set_min_width(150 if index == 0 else 80)
            self.task_view.append_column(column)
        progress_column = Gtk.TreeViewColumn('进度', Gtk.CellRendererProgress(), value=3)
        progress_column.set_min_width(90)
        self.task_view.append_column(progress_column)
        speed_column = Gtk.TreeViewColumn('大小 / 速度', Gtk.CellRendererText(ellipsize=3), text=4)
        speed_column.set_min_width(150)
        self.task_view.append_column(speed_column)
        self.task_action_renderer = TaskActionRenderer(self)
        self.task_action_column = Gtk.TreeViewColumn('', self.task_action_renderer, text=7)
        self.task_action_column.set_min_width(72)
        self.task_view.append_column(self.task_action_column)
        self.task_stack = Gtk.Stack()
        self.task_stack.set_homogeneous(False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 170)
        scroll.add(self.task_view)
        self.task_stack.add_named(scroll, 'tasks')
        empty = Gtk.Label(label='暂无传输任务', xalign=0, margin_top=4, margin_bottom=8)
        empty.get_style_context().add_class('muted')
        self.task_stack.add_named(empty, 'empty')
        main.pack_start(self.task_stack, False, False, 0)
        # Finish cancellation cleanup even when the last GTK window is closed.
        self.worker_thread = threading.Thread(target=self.worker, name='vncming-sftp')
        self.worker_thread.start()
        self.show_all()
        self.update_transfer_actions()
        self.update_task_actions()
        self.local.load(str(Path.home()))

    def worker(self):
        while True:
            operation = self.operations.get()
            if operation is None:
                break
            if self.closed:
                continue
            callback, target = operation
            try:
                callback()
            except Exception as error:
                def show(message=str(error), widget=target):
                    if not self.closed:
                        widget.set_text('操作失败：' + message)
                        widget.set_tooltip_text(message)
                GLib.idle_add(show)
        if self.client:
            self.client.close()
        self.local.worker_thread.join()
        self.other.worker_thread.join()

    def submit(self, callback, target=None):
        if not self.closed:
            self.operations.put((callback, target or self.state))

    def update_transfer_actions(self):
        if self.closed or not hasattr(self, 'other'):
            return
        connected = self.remote is not None and not self.connecting
        self.upload.set_sensitive(bool(connected and self.other.path and not self.other.loading and not self.local.loading and self.local.selected()))
        self.download.set_sensitive(bool(connected and self.local.path and not self.local.loading and not self.other.loading and self.other.selected()))
        self.login_button.set_label('正在连接…' if self.connecting else '连接')
        self.login_button.set_visible(not connected)
        self.login_button.set_sensitive(not self.connecting)
        self.connection_more.set_visible(connected)
        self.connection_actions['重新连接…'].set_sensitive(not any(t['status'] in ACTIVE_TASKS for t in self.tasks))

    def update_task_actions(self):
        if self.closed:
            return
        active = any(t['status'] in ACTIVE_TASKS for t in self.tasks)
        failed = any(t['status'] in ('失败', '已取消') for t in self.tasks)
        finished = any(t['status'] not in ACTIVE_TASKS for t in self.tasks)
        self.task_actions['重试失败任务'].set_sensitive(failed)
        self.task_actions['取消全部传输'].set_sensitive(active)
        self.task_actions['清除已结束任务'].set_sensitive(finished)
        self.task_title.set_text('传输任务' + (f' · {len(self.tasks)}' if self.tasks else ''))
        self.task_stack.set_visible_child_name('tasks' if self.tasks else 'empty')
        self.update_transfer_actions()

    def ask(self, title, text, choices):
        if self.closed:
            return 'cancel'
        event = threading.Event()
        result = ['cancel']
        self.waiters.append(event)
        def prompt():
            if self.closed:
                event.set()
                return
            dialog = AnimatedDialog(title=title, transient_for=self, modal=True)
            label = Gtk.Label(label=text, wrap=True, selectable=True, max_width_chars=60, margin=24)
            dialog.get_content_area().add(label)
            for index, (caption, value) in enumerate(choices):
                dialog.add_button(caption, index + 1)
            dialog.show_all()
            response = dialog.run()
            if 1 <= response <= len(choices):
                result[0] = choices[response - 1][1]
            dialog.destroy()
            event.set()
        GLib.idle_add(prompt)
        while not event.wait(.2):
            if self.closed:
                result[0] = 'cancel'
                break
        self.waiters.remove(event)
        return result[0]

    def login(self, *_):
        if any(task['status'] in ACTIVE_TASKS for task in self.tasks):
            self.state.set_text('请先完成或取消传输任务')
            return
        dialog = AnimatedDialog(title='连接文件传输', transient_for=self, modal=True)
        grid = Gtk.Grid(column_spacing=14, row_spacing=12, margin=24)
        fields = {}
        for row, (key, label, value) in enumerate([
            ('host', '主机', ssh_host(self.entry['address'])),
            ('port', 'SSH 端口', str(self.entry.get('ssh_port', 22))),
            ('user', '用户名', self.entry.get('ssh_username') or self.entry.get('username', '')),
            ('password', 'SSH 密码', '')]):
            field = Gtk.Entry(text=value)
            if key == 'host':
                field.set_editable(False)
                field.set_tooltip_text('使用当前设备的地址')
            if key == 'password':
                field.set_visibility(False)
                field.set_placeholder_text('留空使用 SSH 密钥 / Agent')
            fields[key] = field
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            grid.attach(field, 1, row, 1, 1)
        remember = Gtk.CheckButton(label='将 SSH 密码保存到系统钥匙环')
        grid.attach(remember, 0, 4, 2, 1)
        note = Gtk.Label(label='远程设备需启用 SSH / SFTP；密码可以与 VNC 密码不同。', wrap=True, max_width_chars=45, xalign=0)
        note.get_style_context().add_class('muted')
        grid.attach(note, 0, 5, 2, 1)
        error = Gtk.Label(xalign=0, wrap=True, max_width_chars=45)
        grid.attach(error, 0, 6, 2, 1)
        identity = self.entry.get('credential_id')
        try:
            if identity:
                saved = credentials.lookup(identity + ':sftp')
                fields['password'].set_text(saved)
                remember.set_active(bool(saved))
        except Exception as exception:
            error.set_text('钥匙环读取失败：' + str(exception))
        dialog.get_content_area().add(grid)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '连接', Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.OK:
            try:
                host, user = fields['host'].get_text().strip(), fields['user'].get_text().strip()
                port = int(fields['port'].get_text())
                if not host or not user or not 1 <= port <= 65535:
                    raise ValueError('请输入主机、用户名和有效端口')
                password = fields['password'].get_text()
                if identity:
                    credentials.store(identity + ':sftp', '文件传输 · ' + self.entry['name'], password if remember.get_active() else '')
                self.entry.update(ssh_port=port, ssh_username=user)
                parent = self.get_transient_for()
                if parent and hasattr(parent, 'save'):
                    parent.save()
                self.begin_connect(host, port, user, password)
                break
            except Exception as exception:
                error.set_text(str(exception))
        dialog.destroy()

    def begin_connect(self, host, port, user, password):
        self.connecting = True
        self.state.set_text('正在连接…')
        self.other.set_sensitive(False)
        self.other.generation += 1
        self.other.path = None
        self.other.model.clear()
        self.other.location.set_text('')
        self.update_transfer_actions()
        def run():
            try:
                if self.client:
                    self.client.close()
                self.client = self.remote = self.browse_remote = None
                def approve(hostname, fingerprint):
                    return self.ask('确认远程设备身份', hostname + '\n\n主机指纹\n' + fingerprint + '\n\n请核对后再信任此设备。', [('取消', False), ('信任并连接', True)]) is True
                self.client, self.remote = connect(host, port, user, password, approve)
                # A distinct session avoids sharing SFTP request/response state
                # between the transfer worker and the browser worker.
                channel = self.client.open_sftp()
                channel.get_channel().settimeout(20)
                self.browse_remote = RemoteFiles(channel)
                path = self.remote.normalize('.')
                def ready():
                    if self.closed:
                        return
                    self.state.set_text('已连接 · ' + host)
                    self.other.set_sensitive(True)
                    self.other.load(path, canonical=True)
                GLib.idle_add(ready)
            except Exception:
                if self.client:
                    self.client.close()
                self.client = self.remote = self.browse_remote = None
                raise
            finally:
                def finished():
                    if not self.closed:
                        self.connecting = False
                        self.update_transfer_actions()
                GLib.idle_add(finished)
        self.submit(run)

    def enqueue(self, paths, upload):
        destination = self.other.path if upload else self.local.path
        if not self.remote or not destination:
            (self.other if upload else self.local).note.set_text('请先连接设备并打开目标文件夹')
            return
        # Selecting a directory and its child should not send the child twice.
        separator = '/' if not upload else os.sep
        paths = [p for p in paths if not any(p.startswith(other.rstrip(separator) + separator) for other in paths if p != other)]
        if not paths:
            (self.local if upload else self.other).note.set_text('请先选择文件或文件夹')
        for path in dict.fromkeys(paths):
            task = dict(path=path, destination=destination, upload=upload, cancel=threading.Event(), status='等待中')
            self.tasks.append(task)
            task['iter'] = self.task_model.append([os.path.basename(path.rstrip('/')), '上传' if upload else '下载', '等待中', 0, '', path + '\n→ ' + destination, task, '取消'])
            self.schedule(task)
        self.update_task_actions()

    def schedule(self, task):
        def run():
            if task['cancel'].is_set():
                task['status'] = '已取消'
                GLib.idle_add(self.update_task, task, 0, 0, '已取消', '')
                return
            task['status'] = '正在传输'
            GLib.idle_add(self.update_task, task, 0, 0, '正在传输', '')
            began, last = time.monotonic(), [0]
            def progress(done, total):
                task['done'], task['total'] = done, total
                now = time.monotonic()
                if now - last[0] > .12 or done == total:
                    last[0] = now
                    speed = human_size(done / max(.1, now - began)) + '/s'
                    GLib.idle_add(self.update_task, task, done, total, '正在传输', speed)
            policy = [None]
            def conflict(path):
                if task['cancel'].is_set():
                    return 'cancel'
                if policy[0] is None:
                    policy[0] = self.ask('目标已有同名文件', path + '\n\n本任务后续同名文件也使用此选项。文件夹会合并。', [('取消任务', 'cancel'), ('跳过', 'skip'), ('保留两份', 'rename'), ('覆盖', 'overwrite')])
                return policy[0]
            try:
                local = LocalFiles()
                source, destination = (local, self.remote) if task['upload'] else (self.remote, local)
                skipped = transfer(source, destination, task['path'], task['destination'], task['cancel'], progress, conflict)
                status = '已完成' if not skipped else f'已完成 · 跳过 {skipped} 项'
                task['status'] = status
                GLib.idle_add(self.update_task, task, task.get('done', 0), task.get('total', 0), status, '')
                GLib.idle_add(self.other.refresh if task['upload'] else self.local.refresh)
            except Cancelled:
                task['status'] = '已取消'
                GLib.idle_add(self.update_task, task, 0, 0, '已取消', '')
            except Exception as exception:
                task['status'] = '失败'
                GLib.idle_add(self.update_task, task, task.get('done', 0), task.get('total', 0), '失败', str(exception))
        self.submit(run)

    def update_task(self, task, done, total, status, detail):
        if self.closed:
            return
        row = task['iter']
        if self.task_model.iter_is_valid(row):
            cancelling = task['cancel'].is_set() and status in ACTIVE_TASKS
            if cancelling:
                status = '正在取消'
            summary = human_size(total) if total else ''
            if detail and status in ACTIVE_TASKS:
                summary += (' · ' if summary else '') + detail
            self.task_model.set(row, 2, status, 3, min(100, int(100 * done / total)) if total else (100 if status.startswith('已完成') else 0),
                                4, summary, 5, task['path'] + '\n→ ' + task['destination'] + '\n' + detail,
                                7, '取消' if status in ACTIVE_TASKS and not cancelling else ('重试' if status in ('失败', '已取消') else ''))
            self.update_task_actions()

    def task_action(self, path):
        task = self.task_model[path][6]
        if task['status'] in ACTIVE_TASKS and not task['cancel'].is_set():
            task['cancel'].set()
            self.update_task(task, task.get('done', 0), task.get('total', 0), '正在取消', '')
        elif task['status'] in ('失败', '已取消'):
            self.retry_task(task)

    def task_key_press(self, _, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            model, row = self.task_view.get_selection().get_selected()
            if row:
                self.task_action(model.get_path(row))
                return True
        return False

    def cancel_all(self, *_):
        for task in self.tasks:
            if task['status'] in ACTIVE_TASKS:
                task['cancel'].set()
                self.update_task(task, task.get('done', 0), task.get('total', 0), '正在取消', '')

    def cancel_selected(self, *_):
        model, row = self.task_view.get_selection().get_selected()
        if row and model[row][6]['status'] in ACTIVE_TASKS:
            self.task_action(model.get_path(row))

    def retry_task(self, task):
        task['cancel'].clear()
        task['status'] = '等待中'
        task['done'] = task['total'] = 0
        self.update_task(task, 0, 0, '等待中', '')
        self.schedule(task)

    def retry(self, *_):
        for task in self.tasks:
            if task['status'] in ('失败', '已取消'):
                self.retry_task(task)

    def clear_finished(self, *_):
        for task in list(self.tasks):
            if task['status'] not in ACTIVE_TASKS:
                self.task_model.remove(task['iter'])
                self.tasks.remove(task)
        self.update_task_actions()

    def close_requested(self, *_):
        if any(t['status'] in ACTIVE_TASKS for t in self.tasks):
            dialog = AnimatedDialog(title='停止传输？', transient_for=self, modal=True)
            dialog.get_content_area().add(Gtk.Label(label='关闭此窗口将取消未完成的传输。', margin=24))
            dialog.add_buttons('继续传输', Gtk.ResponseType.CANCEL, '取消传输并关闭', Gtk.ResponseType.OK)
            dialog.show_all()
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return True
        return False

    def shutdown(self, *_):
        self.closed = True
        self.cancel_all()
        for event in list(self.waiters):
            event.set()
        self.operations.put(None)
        self.local.operations.put(None)
        self.other.operations.put(None)
