"""Exercise GTK queue and folder controls using temporary local endpoints."""
import sys
import time
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import viewer
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
    window.remote = LocalFiles()
    window.state.set_text('已连接 · 本地测试端点')
    window.other.set_sensitive(True)
    window.upload.set_sensitive(True)
    window.download.set_sensitive(True)
    window.local.load(str(source)); window.other.load(str(remote))
    until(lambda: window.local.path == str(source) and window.other.path == str(remote))
    pump()
    window.local.view.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    window.upload.clicked()
    until(lambda: window.tasks and window.tasks[0]['status'] == '已完成')
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
    # Capture and dismiss authentication; no real keyring or remote login.
    def dismiss_login():
        for dialog in Gtk.Window.list_toplevels():
            if isinstance(dialog, Gtk.Dialog) and dialog.get_visible():
                screenshot(dialog, 'file-transfer-login.png')
                dialog.response(Gtk.ResponseType.CANCEL)
        return False
    GLib.timeout_add(400, dismiss_login)
    window.login()
    window.destroy()
    GLib.idle_add(lambda: launcher.destroy())
    Gtk.main()
    print('GTK upload/download buttons, queue, folder navigation and login layout passed')
