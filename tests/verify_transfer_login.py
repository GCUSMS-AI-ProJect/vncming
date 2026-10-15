"""Verify automatic transfer login using fake credentials and local endpoints only."""
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import viewer
import file_transfer
from file_transport import LocalFiles
from gi.repository import Gtk


def until(condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.01)
    assert condition(), 'Timed out waiting for automatic login'


with tempfile.TemporaryDirectory() as temporary:
    viewer.DATA = viewer.LEGACY_DATA = Path(temporary) / 'connections.json'
    parent = viewer.Viewer(show_window=False)
    entry = dict(name='Test device', address='192.0.2.20', username='test-user', credential_id='test-id')
    window = file_transfer.TransferWindow(parent, entry)
    original_lookup, original_connect = file_transfer.credentials.lookup, file_transfer.connect
    original_store = file_transfer.credentials.store
    passwords = {'test-id': 'test-password'}
    writes, attempts, prompts = [], [], []
    file_transfer.credentials.lookup = lambda identity: passwords.get(identity, '')
    file_transfer.credentials.store = lambda *args: writes.append(args)

    class Files(LocalFiles):
        def normalize(self, path):
            return temporary if path == '.' else super().normalize(path)
    class Channel:
        def settimeout(self, value): pass
    class SFTP:
        def get_channel(self): return Channel()
        def listdir_attr(self, path): return []
    class Client:
        def close(self): pass
        def open_sftp(self): return SFTP()
    def connect(host, port, user, password, approve):
        attempts.append((host, port, user, password))
        return Client(), Files()
    file_transfer.connect = connect
    window.login = lambda *args, **kwargs: prompts.append(kwargs.get('error_message'))
    try:
        window.auto_connect()
        until(lambda: not window.connecting)
        assert attempts == [('192.0.2.20', 22, 'test-user', 'test-password')]
        assert not prompts and not writes and window.remote is not None
        entry.update(ssh_username='ssh-user', ssh_port=2222)
        passwords['test-id:sftp'] = 'ssh-password'
        window.auto_connect()
        until(lambda: not window.connecting)
        assert attempts[-1] == ('192.0.2.20', 2222, 'ssh-user', 'ssh-password')
        def reject(*args):
            raise RuntimeError('Authentication failed')
        file_transfer.connect = reject
        window.auto_connect()
        until(lambda: bool(prompts))
        assert 'Authentication failed' in prompts[-1]
        assert window.remote is None and not writes
        window.begin_connect('192.0.2.20', 2222, 'wrong-user', 'wrong-password', remember=True)
        until(lambda: not window.connecting)
        assert not writes and entry['ssh_username'] == 'ssh-user'
        # A user-cancelled host identity prompt must not become a password error.
        prompts.clear()
        def cancel(*args): raise file_transfer.Cancelled('cancelled')
        file_transfer.connect = cancel
        window.auto_connect()
        until(lambda: not window.connecting)
        assert not prompts
        # Manual corrections are saved only after a successful connection.
        file_transfer.connect = connect
        window.begin_connect('192.0.2.20', 2222, 'corrected-user', 'corrected-password', remember=True)
        until(lambda: not window.connecting)
        assert writes[-1] == ('test-id:sftp', '文件传输 · Test device', 'corrected-password')
        assert entry['ssh_username'] == 'corrected-user'
    finally:
        file_transfer.credentials.lookup = original_lookup
        file_transfer.credentials.store = original_store
        file_transfer.connect = original_connect
        window.destroy()
        window.worker_thread.join(5)
        parent.destroy()
print('Automatic SSH login, VNC password reuse, corrected SSH credentials, failure prompt and cancellation passed')
