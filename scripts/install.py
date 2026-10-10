#!/usr/bin/python3
"""Install desktop integration that launches this checkout, without sudo."""
import argparse
from pathlib import Path
import os
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent

def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gnome-grid', action='store_true', help='Install the optional GNOME 42 application-grid extension')
    args = parser.parse_args()
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Secret', '1')
    from PIL import Image
    home = Path.home()
    data = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share')))
    binary = home / '.local/bin/vncming'
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text('#!/bin/sh\nexec ' + shlex.quote(str(ROOT / 'vncming')) + ' "$@"\n')
    binary.chmod(0o755)
    applications = data / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / 'vncming.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=VNCMing\nName[zh_CN]=VNCMing\n'
        'Comment=VNCMing 远程桌面连接\nExec=' + desktop_quote(binary) + '\n'
        'Icon=vncming-orange\nTerminal=false\nCategories=Network;RemoteAccess;\n'
        'StartupWMClass=VNCMing\nKeywords=VNCMing;VNC;远程桌面;\n')
    icon_root = data / 'icons/hicolor'
    with Image.open(ROOT / 'assets/vncming-orange.png') as image:
        for size in (16, 24, 32, 48, 64, 128, 256):
            destination = icon_root / f'{size}x{size}/apps/vncming-orange.png'
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.resize((size,size), getattr(Image, 'Resampling', Image).LANCZOS).save(destination)
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
    old, new = config / 'tigervnc-classic/connections.json', config / 'vncming/connections.json'
    if old.exists() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
    if args.gnome_grid:
        target = data / 'gnome-shell/extensions/vncming-app-grid@local'
        target.mkdir(parents=True, exist_ok=True)
        source = ROOT / 'integrations/gnome-shell/vncming-app-grid@local'
        for name in ('extension.js', 'metadata.json'):
            shutil.copy2(source / name, target / name)
        print('GNOME 42 扩展已安装；重新登录后运行 gnome-extensions enable vncming-app-grid@local。')
    for command in (['desktop-file-validate',str(desktop)],
                    ['update-desktop-database',str(applications)],
                    ['gtk-update-icon-cache','-f','-t',str(icon_root)]):
        if shutil.which(command[0]):
            subprocess.run(command, check=True)
    print(f'安装完成：{binary}\n源码目录：{ROOT}\n可在 Show Applications 中启动 VNCMing。')

if __name__ == '__main__':
    main()
