#!/usr/bin/python3
"""Check an extracted package; --gui briefly opens its isolated GTK frontend."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('package', nargs='?', default=str(ROOT / 'dist/vncming_1.0.3_amd64.deb'))
parser.add_argument('--gui', action='store_true')
args = parser.parse_args()
package = Path(args.package).resolve()
with tempfile.TemporaryDirectory(prefix='vncming-deb-check-') as directory:
    stage = Path(directory)
    subprocess.run(['dpkg-deb', '-R', str(package), str(stage)], check=True)
    program = stage / 'usr/lib/vncming'
    for line in (stage / 'DEBIAN/md5sums').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.md5((stage / name).read_bytes()).hexdigest() == digest, name
    for name in ('usr/bin/vncming', 'usr/lib/vncming/vncming',
                 'usr/lib/vncming/build/vncviewer/vncviewer', 'DEBIAN/postinst', 'DEBIAN/postrm'):
        assert os.access(stage / name, os.X_OK), name
    subprocess.run(['desktop-file-validate', str(stage / 'usr/share/applications/vncming.desktop')], check=True)
    for hook in ('postinst', 'postrm'):
        subprocess.run(['sh', '-n', str(stage / 'DEBIAN' / hook)], check=True)
    dependencies = subprocess.check_output(['ldd', str(program / 'build/vncviewer/vncviewer')], text=True)
    assert 'not found' not in dependencies, dependencies
    subprocess.run([str(program / 'vncming'), '--validate'], check=True)
    with tarfile.open(stage / 'usr/share/doc/vncming/source.tar.gz') as source:
        names = source.getnames()
        assert 'vncming/scripts/build-deb.sh' in names
        assert 'vncming/vendor/tigervnc/vncviewer/StyledMessage.h' in names
        assert not any('/build/' in name or '/.git/' in name or
                       name.endswith('/connections.json') or '/__pycache__/' in name for name in names)
    if args.gui:
        code = '''import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
import viewer
from gi.repository import Gtk, GLib
window = viewer.Viewer()
assert Path(viewer.ENGINE).is_file()
assert not window.entries
window.show_all()
GLib.timeout_add(400, lambda: (window.destroy(), False)[1])
Gtk.main()
print('Extracted package GTK startup passed')
'''
        environment = dict(os.environ, XDG_CONFIG_HOME=str(stage / 'isolated-config'))
        subprocess.run(['/usr/bin/python3', '-c', code, str(program / 'app')],
                       env=environment, check=True, timeout=15)
print('DEB checks passed: checksums, permissions, desktop entry, dependencies, source and relocated startup')
