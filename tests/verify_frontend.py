import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from pathlib import Path
from gi.repository import Gtk,Gdk,GLib

def check(Viewer):
    root=Path(__file__).resolve().parent.parent / "build/test-results"
    root.mkdir(parents=True, exist_ok=True)
    window=Viewer()
    window.address.set_text('192.168.1.100')
    def shot(widget,name):
        surface=widget.get_window()
        Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(),*surface.get_origin()[-2:],surface.get_width(),surface.get_height()).savev(str(root/name),'png',[],[])
    def close_dialog(name):
        for dialog in Gtk.Window.list_toplevels():
            if isinstance(dialog,Gtk.Dialog) and dialog.get_visible():
                shot(dialog,name)
                dialog.response(Gtk.ResponseType.CANCEL)
        return False
    def run():
        shot(window,'launcher.png')
        GLib.timeout_add(350,close_dialog,'connection-properties.png')
        window.new_connection()
        GLib.timeout_add(350,close_dialog,'connection-options.png')
        window.show_options()
        menu=window.menu_bar.get_children()[0].get_submenu()
        menu.popup_at_widget(window.menu_bar.get_children()[0],Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        def finish():
            shot(menu,'launcher-menu.png')
            menu.popdown()
            window.destroy()
            print('Frontend properties, options and dropdown rendered successfully')
            return False
        GLib.timeout_add(350,finish)
        return False
    GLib.timeout_add(350,run)
    Gtk.main()
