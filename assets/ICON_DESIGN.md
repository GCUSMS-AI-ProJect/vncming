# VNCMing — Apricot Link

The active icon is `vncming-portal.svg`, an original editable vector mark with
soft apricot and coral connection rings on a cream tile. It has no lettering or
VNC/TigerVNC imagery. The light palette matches the application's light theme.

`vncming-portal.png` is its 1024 × 1024 raster export. Desktop sizes are derived
by `scripts/install.py` and `scripts/package_deb.py`; both old and current icon
names are updated to avoid stale GNOME icons. The desktop application ID stays
`vncming.desktop` so existing favorites keep working.

The earlier generated portal concept is retained in `output/imagegen/` as design
history; it is not the active icon. This revision is authored directly as SVG
and rendered with librsvg, without an image-generation API.

To regenerate the PNG with the Ubuntu Python packages python3-gi,
python3-cairo and gir1.2-rsvg-2.0:

```python
import cairo
import gi
gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg
surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1024, 1024)
viewport = Rsvg.Rectangle()
viewport.x = viewport.y = 0
viewport.width = viewport.height = 1024
Rsvg.Handle.new_from_file('assets/vncming-portal.svg').render_document(
    cairo.Context(surface), viewport)
surface.write_to_png('assets/vncming-portal.png')
```
