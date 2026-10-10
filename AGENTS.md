# VNCMing maintenance

This repository is the canonical source for VNCMing. Edit `app/` for the GTK
launcher and `vendor/tigervnc/vncviewer/` for the native viewer. Do not edit the
archived copy under `software/tigervnc-classic`.

- Build with `./scripts/build.sh`; start with `./vncming`.
- Install the user desktop entry with `./install.sh` after moving the checkout.
- Preserve credentials in the system keyring; never commit user configuration,
  passwords, logs, certificates, or desktop screenshots.
- Keep `vncming.desktop` and `StartupWMClass=VNCMing` stable for GNOME favorites.
- Native authentication dialogs must hide immediately when dismissed; animated
  closing can re-enter the RFB decoder. Opening animations are supported.
- Use `./scripts/check.sh` for headless validation. GUI regression commands are
  documented in `docs/DEVELOPMENT.md`; do not interact with real remote devices
  for automated UI tests.
- A hostname mismatch may be accepted only for the host explicitly approved by
  the user. Keep other certificate checks and confirmation result values intact.
- Keep upstream notices and licenses in the vendored TigerVNC source.
