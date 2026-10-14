"""Saved connection suggestions that keep keyboard focus in the address field."""
from gi.repository import Gtk, Gdk


class AddressSuggestions:
    def __init__(self, entry, connections):
        self.entry, self.connections = entry, connections
        self.filling = False
        self.popup = Gtk.Popover.new(entry)
        self.popup.set_modal(False)
        self.popup.set_position(Gtk.PositionType.BOTTOM)
        self.popup.get_style_context().add_class('address-suggestions')
        self.rows = Gtk.ListBox()
        self.rows.set_can_focus(False)
        self.rows.set_activate_on_single_click(True)
        self.rows.connect('row-activated', self.choose)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_max_content_height(300)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.add(self.rows)
        self.popup.add(self.scroll)
        entry.connect('changed', self.update)
        entry.connect('focus-in-event', self.update)
        entry.connect('focus-out-event', lambda *_: self.popup.popdown())
        entry.connect('key-press-event', self.key_pressed)
        entry.connect('size-allocate', self.resize)

    def resize(self, *_):
        self.scroll.set_size_request(max(240, self.entry.get_allocated_width() - 24), -1)

    def update(self, *_):
        if self.filling:
            return False
        query = self.entry.get_text().strip().casefold()
        for row in self.rows.get_children():
            self.rows.remove(row)
        if query and self.entry.has_focus():
            for connection in self.connections():
                if not any(query in connection[key].casefold() for key in ('address', 'name')):
                    continue
                row = Gtk.ListBoxRow()
                row.set_can_focus(False)
                row.connection = connection
                box = Gtk.Box(spacing=12, margin=10)
                icon = Gtk.Image.new_from_icon_name('video-display-symbolic', Gtk.IconSize.MENU)
                box.pack_start(icon, False, False, 2)
                labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                name = Gtk.Label(label=connection['name'], xalign=0, ellipsize=3)
                name.get_style_context().add_class('suggestion-name')
                address = Gtk.Label(label=connection['address'], xalign=0, ellipsize=3)
                address.get_style_context().add_class('suggestion-address')
                labels.pack_start(name, False, False, 0)
                labels.pack_start(address, False, False, 0)
                box.pack_start(labels, True, True, 0)
                row.add(box)
                self.rows.add(row)
        if self.rows.get_children():
            self.resize()
            self.popup.show_all()
            self.popup.popup()
        else:
            self.popup.popdown()
        return False

    def choose(self, _, row):
        self.filling = True
        self.entry.set_text(row.connection['address'])
        self.entry.set_position(-1)
        self.filling = False
        self.popup.popdown()
        self.entry.grab_focus()

    def key_pressed(self, _, event):
        if event.keyval == Gdk.KEY_Escape and self.popup.get_visible():
            self.popup.popdown()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            if not self.popup.get_visible():
                self.update()
            rows = self.rows.get_children()
            if not rows or not self.popup.get_visible():
                return False
            selected = self.rows.get_selected_row()
            direction = 1 if event.keyval == Gdk.KEY_Down else -1
            index = (selected.get_index() + direction) % len(rows) if selected else (0 if direction == 1 else len(rows) - 1)
            row = rows[index]
            self.rows.select_row(row)
            adjustment = self.scroll.get_vadjustment()
            allocation = row.get_allocation()
            adjustment.clamp_page(allocation.y, allocation.y + allocation.height)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.popup.get_visible():
            row = self.rows.get_selected_row()
            if row:
                self.choose(self.rows, row)
                return True
        return False
