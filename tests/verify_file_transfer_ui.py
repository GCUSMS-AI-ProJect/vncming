"""Exercise GTK queue and folder controls using temporary local endpoints."""
import sys
import time
import tempfile
import threading
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import viewer
import file_transfer
from file_transfer import TransferWindow
from file_transport import LocalFiles
from gi.repository import Gtk, Gdk, GLib


def pump(seconds=.5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.01)


def until(condition):
    end = time.monotonic() + 8
    while not condition() and time.monotonic() < end: pump(.05)
    assert condition(), 'UI operation did not finish'


def screenshot(window, name):
    surface = window.get_window()
    output = Path(__file__).resolve().parent.parent / 'build/test-results' / name
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), *surface.get_origin()[-2:], surface.get_width(), surface.get_height()).savev(str(output), 'png', [], [])

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    viewer.DATA = viewer.LEGACY_DATA = root / 'connections.json'
    launcher = viewer.Viewer(show_window=False)
    source, remote, output = root / 'local', root / 'remote', root / 'output'
    source.mkdir(); remote.mkdir(); output.mkdir()
    folder = source / '项目文件'
    (folder / '空目录').mkdir(parents=True)
    (folder / '说明.txt').write_text('文件传输测试')
    entry = {'name': '树莓派', 'address': '192.0.2.173', 'username': 'pi'}
    window = TransferWindow(launcher, entry)
    assert window.task_stack.get_visible_child_name() == 'empty'
    assert not any(action.get_sensitive() for action in window.task_actions.values())
    window.remote = window.browse_remote = LocalFiles()
    window.state.set_text('已连接 · 本地测试端点')
    window.other.set_sensitive(True)
    window.local.load(str(source)); window.other.load(str(remote))
    until(lambda: window.local.path == str(source) and window.other.path == str(remote))
    window.update_transfer_actions()
    assert not window.upload.get_sensitive() and not window.download.get_sensitive()
    assert not window.login_button.get_visible() and window.connection_more.get_visible()
    pump()
    window.local.view.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    assert window.upload.get_sensitive() and not window.download.get_sensitive()
    window.upload.clicked()
    until(lambda: window.tasks and window.tasks[0]['status'] == '已完成')
    assert window.task_stack.get_visible_child_name() == 'tasks'
    assert not window.task_actions['取消全部传输'].get_sensitive()
    assert window.task_actions['清除已结束任务'].get_sensitive()
    assert not window.task_model[0][7]
    assert (remote / folder.name / '说明.txt').read_text() == '文件传输测试'
    assert (remote / folder.name / '空目录').is_dir()
    until(lambda: len(window.other.model) == 1)
    window.local.load(str(output))
    until(lambda: window.local.path == str(output))
    window.other.view.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    window.download.clicked()
    until(lambda: len(window.tasks) == 2 and window.tasks[-1]['status'] == '已完成')
    assert (output / folder.name / '说明.txt').read_text() == '文件传输测试'
    pump()
    screenshot(window, 'file-transfer-preview.png')
    window.other.open_row(window.other.view, Gtk.TreePath.new_from_indices([0]), None)
    until(lambda: window.other.path == str(remote / folder.name))
    window.other.parent()
    until(lambda: window.other.path == str(remote))
    window.clear_finished()
    assert len(window.task_model) == 0
    assert window.task_stack.get_visible_child_name() == 'empty'
    pump()
    assert window.task_stack.get_allocated_height() < 100, 'Empty queue must collapse'
    # Cancel through the row renderer while a task is still queued; retry the
    # same row after cleanup and verify that it completes on the local fixture.
    gate = threading.Event()
    window.submit(lambda: gate.wait(5))
    # Browsing must complete while a transfer worker is blocked.
    window.other.load(str(remote / folder.name))
    until(lambda: window.other.path == str(remote / folder.name))
    assert not gate.is_set()
    window.other.parent()
    until(lambda: window.other.path == str(remote))
    window.enqueue([str(folder)], True)
    assert window.task_model[0][7] == '取消'
    assert not window.connection_actions['重新连接…'].get_sensitive()
    def click_task_action():
        window.present()
        pump()
        subprocess.run(['xdotool', 'windowactivate', '--sync', str(window.get_window().get_xid())], check=True)
        area = window.task_view.get_cell_area(Gtk.TreePath.new_from_indices([0]), window.task_action_column)
        x, y = window.task_view.get_bin_window().get_origin()[-2:]
        subprocess.run(['xdotool', 'mousemove', str(x + area.x + area.width // 2), str(y + area.y + area.height // 2), 'click', '1'], check=True)
        pump(.1)
    click_task_action()
    assert window.tasks[0]['cancel'].is_set()
    gate.set()
    until(lambda: window.tasks[0]['status'] == '已取消')
    pump()
    assert window.task_model[0][7] == '重试'
    original_ask = window.ask
    window.ask = lambda *_: 'overwrite'
    click_task_action()
    until(lambda: window.tasks[0]['status'] == '已完成')
    window.ask = original_ask
    window.clear_finished()
    # Capture and dismiss authentication; no real keyring or remote login.
    def dismiss_login():
        for dialog in Gtk.Window.list_toplevels():
            if isinstance(dialog, Gtk.Dialog) and dialog.get_visible():
                screenshot(dialog, 'file-transfer-login.png')
                dialog.response(Gtk.ResponseType.CANCEL)
        return False
    GLib.timeout_add(400, dismiss_login)
    window.login()
    original_connect = file_transfer.connect
    class FixtureSFTP:
        def get_channel(self): return self
        def settimeout(self, value): pass
        def normalize(self, path): return str(remote) if path == '.' else path
        def listdir_attr(self, path):
            import paramiko
            result = []
            for name, info in LocalFiles().listing(path):
                item = paramiko.SFTPAttributes.from_stat(info)
                item.filename = name
                result.append(item)
            return result
    class FixtureClient:
        def close(self): pass
        def open_sftp(self): return FixtureSFTP()
    class FixtureRemote(LocalFiles):
        def normalize(self, path):
            return str(remote) if path == '.' else super().normalize(path)
    file_transfer.connect = lambda *_: (FixtureClient(), FixtureRemote())
    try:
        window.begin_connect('192.0.2.173', 22, 'test-user', '')
        assert not window.login_button.get_sensitive()
        assert not window.upload.get_sensitive() and not window.download.get_sensitive()
        until(lambda: not window.connecting and window.other.path == str(remote))
        assert window.other.get_sensitive() and window.connection_more.get_visible()
        assert not window.upload.get_sensitive(), 'No selection after reconnect'
        def fail(*_): raise RuntimeError('Simulated connection failure')
        file_transfer.connect = fail
        window.begin_connect('192.0.2.173', 22, 'test-user', '')
        until(lambda: not window.connecting and window.remote is None)
        assert window.login_button.get_visible() and window.login_button.get_sensitive()
        assert not window.connection_more.get_visible()
        assert not window.upload.get_sensitive() and not window.download.get_sensitive()
    finally:
        file_transfer.connect = original_connect
    # Discard queued obsolete reads and ignore errors from superseded paths.
    started, release = threading.Event(), threading.Event()
    calls = []
    class SlowFiles(LocalFiles):
        def listing(self, path):
            calls.append(path)
            if path == str(source):
                started.set()
                release.wait(5)
                raise OSError('obsolete read failure')
            return super().listing(path)
    window.browse_remote = SlowFiles()
    window.other.load(str(source))
    assert started.wait(2)
    window.other.load(str(output))
    window.other.load(str(remote))
    release.set()
    until(lambda: window.other.path == str(remote) and not window.other.loading)
    assert calls == [str(source), str(remote)], calls
    assert '失败' not in window.other.note.get_text()
    # Large directories reuse two decoded SVGs, and render in GTK idle batches.
    large = root / 'large'
    large.mkdir()
    for index in range(1500): (large / f'{index:04}.txt').touch()
    (large / 'folder').mkdir()
    file_transfer.icon_pixbuf.cache_clear()
    began = time.monotonic()
    window.local.load(str(large))
    until(lambda: window.local.path == str(large) and not window.local.loading)
    elapsed = time.monotonic() - began
    assert len(window.local.model) == 1501
    assert file_transfer.icon_pixbuf.cache_info().misses == 2
    print(f'1501 directory entries rendered in {elapsed:.3f}s; only 2 SVG decodes')
    window.destroy()
    GLib.idle_add(lambda: launcher.destroy())
    Gtk.main()
    print('GTK upload/download buttons, queue, folder navigation and login layout passed')
