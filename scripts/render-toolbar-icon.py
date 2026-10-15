#!/usr/bin/python3
"""Render the toolbar SVG for the native FLTK 1.3 client (no SVG image loader)."""
from pathlib import Path
import gi

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

source = Path(__file__).resolve().parent.parent / 'assets/transfer/toolbar-transfer.svg'
loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
loader.set_size(24, 24)
loader.write(source.read_bytes())
loader.close()
loader.get_pixbuf().savev(str(source.with_suffix('.png')), 'png', [], [])
