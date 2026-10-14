"""Exercise matching and selection without reading real connections or connecting."""
import sys
import tempfile
import time
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import viewer
from gi.repository import Gtk, Gdk, GLib


def pump():
    deadline = time.monotonic() + .25
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.01)


with tempfile.TemporaryDirectory() as temporary:
    viewer.DATA = viewer.LEGACY_DATA = Path(temporary) / 'connections.json'
    window = viewer.Viewer()
    window.entries = [
        {'name': '树莓派', 'address': '192.0.2.173'},
        {'name': '工作电脑', 'address': '198.51.100.173::5901'},
        {'name': '测试设备', 'address': '172.16.4.25'},
    ]
    window.refresh()
    window.present()
    pump()
    subprocess.run(['xdotool', 'windowactivate', '--sync', str(window.get_window().get_xid())], check=True)
    window.address.grab_focus()
    pump()
    # Let the empty-to-list crossfade finish before capturing the new layout.
    pump()
    pump()
    surface = window.get_window()
    output = Path(__file__).resolve().parent.parent / 'build/test-results'
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), *surface.get_origin()[-2:], surface.get_width(), surface.get_height()).savev(str(output / 'connections-theme.png'), 'png', [], [])
    suggestions = window.suggestions
    def search(query, expected):
        window.address.set_text(query)
        pump()
        actual = [r.connection['address'] for r in suggestions.rows.get_children()]
        assert actual == expected, (query, actual)
        assert suggestions.popup.get_visible() == bool(expected)
        assert window.address.has_focus(), 'typing focus moved to popup'
    search('192', ['192.0.2.173'])
    search('0', ['192.0.2.173', '198.51.100.173::5901'])
    search('173', ['192.0.2.173', '198.51.100.173::5901'])
    search('树莓', ['192.0.2.173'])
    search('not-saved', [])
    search('', [])
    search(' 0 ', ['192.0.2.173', '198.51.100.173::5901'])
    def key(name):
        subprocess.run(['xdotool', 'key', name], check=True)
        pump()
    key('Down')
    key('Down')
    assert suggestions.rows.get_selected_row().get_index() == 1
    key('Return')
    assert window.address.get_text() == '198.51.100.173::5901'
    assert not suggestions.popup.get_visible()
    received = []
    window.start_connection = lambda address, entry: received.append((address, entry))
    window.connect_address()
    assert received == [('198.51.100.173::5901', window.entries[1])]
    search('0', ['192.0.2.173', '198.51.100.173::5901'])
    row = suggestions.rows.get_children()[0]
    x, y = row.translate_coordinates(window, 30, 20)
    origin = window.get_window().get_origin()[-2:]
    subprocess.run(['xdotool', 'mousemove', str(origin[0]+x), str(origin[1]+y), 'click', '1'], check=True)
    pump()
    assert window.address.get_text() == '192.0.2.173', 'mouse selection failed'
    assert not suggestions.popup.get_visible()
    window.address.grab_focus()
    search('173', ['192.0.2.173', '198.51.100.173::5901'])
    result = Path(__file__).resolve().parent.parent / 'build/test-results/suggestions.png'
    surface = window.get_window()
    Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), *surface.get_origin()[-2:], surface.get_width(), surface.get_height()).savev(str(result), 'png', [], [])
    key('Escape')
    assert not suggestions.popup.get_visible()
    # Changes in the saved list are reflected immediately on the next search.
    window.entries.pop(0)
    search('0', ['198.51.100.173::5901'])
    GLib.idle_add(lambda: window.destroy())
    Gtk.main()
    print('Substring matches, keyboard/mouse selection, saved configuration reuse and dismissal passed')
