import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
"""Check sheet animation lifecycle without modifying saved connections."""
import json
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from viewer import Viewer
from motion import AnimatedDialog

window = Viewer()
dialog = AnimatedDialog(title='动画检查', transient_for=window, modal=True)
dialog.add_button('好', Gtk.ResponseType.OK)
dialog.get_content_area().add(Gtk.Label(label='VNCMing'))
result = {}
dialog.connect('destroy', lambda *_: result.update(destroyed=True))
dialog.show_all()

def sample_open():
    result['opening_opacity'] = dialog.get_opacity()
    return False

def close():
    result['opened_opacity'] = dialog.get_opacity()
    dialog.destroy()
    return False

def sample_close():
    result['closing_opacity'] = dialog.get_opacity()
    return False

def finish():
    window.destroy()
    return False

GLib.timeout_add(60, sample_open)
GLib.timeout_add(300, close)
GLib.timeout_add(350, sample_close)
GLib.timeout_add(550, finish)
Gtk.main()
assert 0 < result['opening_opacity'] < 1, result
assert result['opened_opacity'] == 1, result
assert 0 < result['closing_opacity'] < 1, result
assert result.get('destroyed'), result
print(json.dumps(result))
