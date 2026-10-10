"""Animated GTK sheets for VNCMing."""
from gi.repository import Gtk, GLib


def animate_menu(menu):
    def opened(widget):
        began = GLib.get_monotonic_time()
        widget.set_opacity(0)
        def step(widget, clock):
            t = min(1, (GLib.get_monotonic_time() - began) / 140000)
            widget.set_opacity(1 - (1 - t) ** 3)
            return t < 1 and widget.get_mapped()
        widget.add_tick_callback(step)
    menu.connect('map', opened)


class AnimatedDialog(Gtk.Dialog):
    def __init__(self, *args, **kwargs):
        kwargs['use_header_bar'] = True
        super().__init__(*args, **kwargs)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_resizable(False)
        self.get_style_context().add_class('apple-sheet')
        self._tick = None
        self._closing = False
        self.connect('map', self._on_map)
        self.connect('delete-event', self._on_delete)

    def _on_delete(self, *_):
        self.response(Gtk.ResponseType.CANCEL)
        return True

    def _animate(self, end, done=None):
        if self._tick is not None:
            self.remove_tick_callback(self._tick)
        start = self.get_opacity()
        began = GLib.get_monotonic_time()
        duration = 200000 if end else 140000
        def step(widget, clock):
            t = min(1, (GLib.get_monotonic_time() - began) / duration)
            eased = 1 - (1 - t) ** 3
            self.set_opacity(start + (end - start) * eased)
            if t >= 1:
                self._tick = None
                if done:
                    done()
                return False
            return True
        self._tick = self.add_tick_callback(step)

    def _on_map(self, *_):
        self.set_opacity(0)
        self._animate(1)

    def destroy(self):
        if self._closing:
            return
        self._closing = True
        if not self.get_mapped():
            Gtk.Dialog.destroy(self)
            return
        self.set_sensitive(False)
        self._animate(0, lambda: Gtk.Dialog.destroy(self))
