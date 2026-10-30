"""Check parent/forward directory navigation with local fixtures and no input events."""
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from file_transfer import Browser
from file_transport import LocalFiles


def until(condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.005)
    assert condition(), 'Directory navigation did not complete'


class Owner:
    closed = False
    entry = {'name': 'Test device', 'address': '192.0.2.20'}
    remote = browse_remote = LocalFiles()
    def update_transfer_actions(self): pass


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    parent = root / '父目录'
    child = parent / '子目录'
    child.mkdir(parents=True)
    other = root / '其他目录'
    other.mkdir()
    owner = Owner()
    panes = [Browser(owner, False), Browser(owner, True)]
    try:
        for pane in panes:
            pane.load(str(child))
            until(lambda: not pane.loading)
            assert not pane.path_buttons[1].get_sensitive()
            pane.path_buttons[0].clicked()
            assert not pane.path_buttons[1].get_sensitive(), 'Loading must disable forward'
            until(lambda: not pane.loading)
            assert pane.path == str(parent)
            assert pane.path_buttons[1].get_sensitive()
            pane.parent()
            until(lambda: not pane.loading)
            assert pane.path == str(root)
            pane.path_buttons[1].clicked()
            until(lambda: not pane.loading)
            assert pane.path == str(parent)
            pane.refresh()
            until(lambda: not pane.loading)
            assert pane.path_buttons[1].get_sensitive(), 'Refresh must preserve forward history'
            pane.forward()
            until(lambda: not pane.loading)
            assert pane.path == str(child) and not pane.forward_paths
            pane.parent()
            until(lambda: not pane.loading)
            pane.load(str(other))
            until(lambda: not pane.loading)
            assert not pane.forward_paths and not pane.path_buttons[1].get_sensitive()
        # A missing/deleted destination must not discard the last child path.
        pane = panes[0]
        pane.load(str(child))
        until(lambda: not pane.loading)
        pane.parent()
        until(lambda: not pane.loading)
        child.rmdir()
        pane.forward()
        until(lambda: not pane.loading)
        assert pane.path == str(parent) and pane.forward_paths == [str(child)]
        child.mkdir()
        pane.forward()
        until(lambda: not pane.loading)
        assert pane.path == str(child) and not pane.forward_paths
        assert panes[1].path == str(other) and not panes[1].forward_paths
    finally:
        owner.closed = True
        for pane in panes:
            pane.operations.put(None)
            pane.worker_thread.join(5)
            pane.destroy()
print('Both panes: parent/forward navigation, multiple levels, refresh, branching, failed destination and independent histories passed')
