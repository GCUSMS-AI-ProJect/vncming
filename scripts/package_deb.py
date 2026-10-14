#!/usr/bin/python3
"""Build a self-contained user-interface Debian package without root."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HOMEPAGE = 'https://github.com/GCUSMS-AI-ProJect/vncming'


def write(path, text, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755 if executable else 0o644)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='1.0.3')
    args = parser.parse_args()
    subprocess.run(['dpkg', '--validate-version', args.version], check=True)
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    for tool in ('dpkg-deb', 'dpkg-shlibdeps', 'strip', 'desktop-file-validate'):
        if not shutil.which(tool):
            raise SystemExit(f'缺少 {tool}；请先运行 ./scripts/install-deps.sh')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    package = dist / f'vncming_{args.version}_{architecture}.deb'
    with tempfile.TemporaryDirectory(prefix='deb-', dir=dist) as directory:
        work = Path(directory)
        stage = work / 'debian/vncming'
        program = stage / 'usr/lib/vncming'
        for path in (ROOT / 'app').iterdir():
            if path.suffix in ('.py', '.css'):
                copy(path, program / 'app' / path.name)
        copy(ROOT / 'assets/vncming-orange.png', program / 'assets/vncming-orange.png')
        for directory in ('transfer', 'actions'):
            for path in (ROOT / 'assets' / directory).iterdir():
                if path.is_file():
                    copy(path, program / 'assets' / directory / path.name)
        copy(ROOT / 'vncming', program / 'vncming')
        (program / 'vncming').chmod(0o755)
        native = program / 'build/vncviewer/vncviewer'
        copy(ROOT / 'build/vncviewer/vncviewer', native)
        native.chmod(0o755)
        subprocess.run(['strip', '--strip-unneeded', str(native)], check=True)
        write(stage / 'usr/bin/vncming', '#!/bin/sh\nexec /usr/lib/vncming/vncming "$@"\n', True)
        desktop = stage / 'usr/share/applications/vncming.desktop'
        write(desktop, '[Desktop Entry]\nType=Application\nName=VNCMing\nName[zh_CN]=VNCMing\n'
              'Comment=VNC remote desktop client\nComment[zh_CN]=VNC 远程桌面连接\n'
              'Exec=/usr/bin/vncming\nIcon=vncming-orange\nTerminal=false\n'
              'Categories=Network;RemoteAccess;\nStartupWMClass=VNCMing\n'
              'Keywords=VNCMing;VNC;远程桌面;\n')
        subprocess.run(['desktop-file-validate', str(desktop)], check=True)
        for name in ('extension.js', 'metadata.json'):
            copy(ROOT / 'integrations/gnome-shell/vncming-app-grid@local' / name,
                 stage / 'usr/share/gnome-shell/extensions/vncming-app-grid@local' / name)
        with Image.open(ROOT / 'assets/vncming-orange.png') as image:
            for size in (16, 24, 32, 48, 64, 128, 256):
                icon = stage / f'usr/share/icons/hicolor/{size}x{size}/apps/vncming-orange.png'
                icon.parent.mkdir(parents=True, exist_ok=True)
                image.resize((size, size), getattr(Image, 'Resampling', Image).LANCZOS).save(icon)
                icon.chmod(0o644)
        doc = stage / 'usr/share/doc/vncming'
        for name in ('README.md', 'NOTICE.md', 'LICENSE'):
            copy(ROOT / name, doc / name)
        copyright_file = ROOT / 'vendor/tigervnc/contrib/packages/deb/ubuntu-focal/debian/copyright'
        copy(copyright_file, doc / 'copyright')
        # Include matching source, licenses and build tools in the binary package.
        # Only project source directories are included; configuration and build output
        # are outside this allowlist. Never archive the user's home directory.
        source_paths = ('app', 'assets', 'vendor', 'scripts', 'tests', 'integrations', 'docs',
                        'README.md', 'NOTICE.md', 'LICENSE', 'AGENTS.md', '.gitignore',
                        '.github', 'vncming', 'viewer.py', 'install.sh')
        def source_filter(member):
            path = Path(member.name)
            if any(part in ('.git', '__pycache__', '.venv') for part in path.parts):
                return None
            if path.suffix in ('.pyc', '.pyo', '.log', '.o', '.a', '.pem', '.key'):
                return None
            member.uid = member.gid = 0
            member.uname = member.gname = 'root'
            member.mode = 0o755 if member.isdir() or member.mode & 0o111 else 0o644
            return member
        with tarfile.open(doc / 'source.tar.gz', 'w:gz') as archive:
            for name in source_paths:
                archive.add(ROOT / name, arcname=f'vncming/{name}', filter=source_filter)
        (doc / 'source.tar.gz').chmod(0o644)
        basic_control = (f'Package: vncming\nVersion: {args.version}\nSection: net\nPriority: optional\n'
                         f'Architecture: {architecture}\n'
                         'Maintainer: VNCMing contributors <noreply@github.com>\n')
        write(work / 'debian/control',
              'Source: vncming\nSection: net\nPriority: optional\n'
              'Maintainer: VNCMing contributors <noreply@github.com>\n\n'
              'Package: vncming\nArchitecture: any\n'
              'Description: VNCMing VNC remote desktop client\n')
        shlibs = subprocess.check_output(['dpkg-shlibdeps', '-O', '-e' + str(native)], cwd=work, text=True)
        native_dependencies = next(line.split('=', 1)[1] for line in shlibs.splitlines()
                                   if line.startswith('shlibs:Depends='))
        size = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())
        control = stage / 'DEBIAN'
        write(control / 'control', basic_control +
              f'Installed-Size: {(size + 1023) // 1024}\n'
              f'Depends: {native_dependencies}, python3 (>= 3.10), python3-gi, python3-pil, python3-paramiko, '
              'gir1.2-gtk-3.0, gir1.2-secret-1, fonts-noto-cjk\n'
              'Recommends: gnome-keyring\n'
              f'Homepage: {HOMEPAGE}\n'
              'Description: VNCMing VNC remote desktop client\n'
              ' Orange GTK connection manager and customized TigerVNC viewer with\n'
              ' keyring credentials, styled dialogs, full-screen scaling and\n'
              ' per-connection editing. Runs in a Linux X11 desktop session.\n')
        for hook in ('postinst', 'postrm'):
            write(control / hook, '#!/bin/sh\nset -e\n'
                  'if command -v update-desktop-database >/dev/null 2>&1; then\n'
                  '    update-desktop-database -q /usr/share/applications || true\nfi\n'
                  'if command -v gtk-update-icon-cache >/dev/null 2>&1; then\n'
                  '    gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true\nfi\n'
                  'exit 0\n', True)
        lines = []
        for path in sorted((stage / 'usr').rglob('*')):
            if path.is_file():
                lines.append(f'{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(stage)}\n')
        write(control / 'md5sums', ''.join(lines))
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(package)], check=True)
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    write(Path(str(package) + '.sha256'), f'{checksum}  {package.name}\n')
    print(f'安装包：{package}\n安装：sudo apt install ./{package.name}')


if __name__ == '__main__':
    main()
