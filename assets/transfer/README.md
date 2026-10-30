# Transfer icons

Most icons are from [Lucide](https://github.com/lucide-icons/lucide), retrieved
2026-10-13. ISC / MIT notices are retained in `LICENSE`.

`toolbar-transfer.svg` is the official Tabler **arrows-exchange** SVG:
https://github.com/tabler/tabler-icons/blob/main/icons/outline/arrows-exchange.svg
Retrieved 2026-10-15; upstream Git blob `90113e107333a997ef9eff4f9ebea8be656ba5eb`.
MIT notice retained in `LICENSE.tabler`.

`upload.svg` and `download.svg` are the official Lucide originals retrieved
2026-10-15:
- https://github.com/lucide-icons/lucide/blob/main/icons/upload.svg
  Git blob `ce355073f92b8947dd9e439c6ff67e6a13b837ae`.
- https://github.com/lucide-icons/lucide/blob/main/icons/download.svg
  Git blob `5c75527bde1fe8259efb72c5b590bedfae28c05e`.

Only `currentColor` is replaced with VNCMing accent `#a44d14`; SVG paths, stroke
widths, line caps and geometry are unchanged. These three icons are not custom
drawings. FLTK 1.3 uses `toolbar-transfer.png`, generated from the SVG with:

```sh
/usr/bin/python3 scripts/render-toolbar-icon.py
```

`arrow-down.svg` is the official Lucide icon used for forward navigation:
https://github.com/lucide-icons/lucide/blob/main/icons/arrow-down.svg
Upstream Git blob `3244b63e3147e5e8b359f20458106bc74572d331`; only the stroke
color is adapted, with the same Lucide license in `LICENSE`.
