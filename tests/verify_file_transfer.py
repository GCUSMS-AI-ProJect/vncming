"""Real localhost SFTP roundtrips; never touch user devices or credentials."""
import errno
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import paramiko
from file_transport import RemoteFiles, LocalFiles, Cancelled, connect, ssh_host, transfer


class Server(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if (username, password) == ('test', 'fixture') else paramiko.AUTH_FAILED
    def get_allowed_auths(self, username):
        return 'password'
    def check_channel_request(self, kind, channel):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class SFTP(paramiko.SFTPServerInterface):
    def __init__(self, server, root):
        super().__init__(server)
        self.root = Path(root)
    def path(self, path):
        target = (self.root / path.lstrip('/')).resolve()
        if not target.is_relative_to(self.root):
            raise PermissionError(errno.EACCES, 'outside fixture')
        return str(target)
    def canonicalize(self, path):
        return '/' + os.path.relpath(self.path(path), str(self.root)).removeprefix('.') .lstrip('/')
    def stat(self, path):
        try: return paramiko.SFTPAttributes.from_stat(os.lstat(self.path(path)))
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    lstat = stat
    def list_folder(self, path):
        try:
            items = []
            for name in os.listdir(self.path(path)):
                info = paramiko.SFTPAttributes.from_stat(os.lstat(os.path.join(self.path(path), name)))
                info.filename = name
                items.append(info)
            return items
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    def open(self, path, flags, attr):
        try:
            fd = os.open(self.path(path), flags, 0o600)
            mode = 'r+b' if flags & os.O_RDWR else ('wb' if flags & os.O_WRONLY else 'rb')
            file = os.fdopen(fd, mode)
            handle = paramiko.SFTPHandle(flags)
            handle.readfile = handle.writefile = file
            return handle
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    def mkdir(self, path, attr):
        try: os.mkdir(self.path(path)); return paramiko.SFTP_OK
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    def remove(self, path):
        try: os.unlink(self.path(path)); return paramiko.SFTP_OK
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    def rename(self, source, destination):
        try:
            os.link(self.path(source), self.path(destination))
            os.unlink(self.path(source))
            return paramiko.SFTP_OK
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)
    def posix_rename(self, source, destination):
        try: os.replace(self.path(source), self.path(destination)); return paramiko.SFTP_OK
        except OSError as error: return paramiko.SFTPServer.convert_errno(error.errno)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        remote_root = root / 'remote'
        remote_root.mkdir()
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(.2)
        port = listener.getsockname()[1]
        key = [paramiko.RSAKey.generate(2048)]
        stopped = threading.Event()
        transports = []
        def serve():
            while not stopped.is_set():
                try: channel, _ = listener.accept()
                except socket.timeout: continue
                except OSError: break
                def session(channel=channel):
                    transport = paramiko.Transport(channel)
                    transports.append(transport)
                    transport.add_server_key(key[0])
                    transport.set_subsystem_handler('sftp', paramiko.SFTPServer, SFTP, root=remote_root)
                    try: transport.start_server(server=Server())
                    except (EOFError, paramiko.SSHException): pass
                threading.Thread(target=session, daemon=True).start()
        threading.Thread(target=serve, daemon=True).start()
        client = None
        try:
            known = root / 'known'
            approvals = []
            def approve(host, fingerprint):
                approvals.append(fingerprint)
                return True
            client, remote = connect('127.0.0.1', port, 'test', 'fixture', approve, known)
            assert approvals and known.exists()
            local = LocalFiles()
            source = root / '源 目录'
            (source / '空文件夹').mkdir(parents=True)
            (source / '子目录').mkdir()
            payload = os.urandom(450000)
            (source / '子目录' / '中文 空格.bin').write_bytes(payload)
            (source / 'empty.txt').write_bytes(b'')
            event = threading.Event()
            progress = []
            assert transfer(local, remote, str(source), '/', event, lambda n, total: progress.append((n,total))) == 0
            assert (remote_root / source.name / '子目录' / '中文 空格.bin').read_bytes() == payload
            assert (remote_root / source.name / '空文件夹').is_dir()
            assert progress[-1] == (len(payload), len(payload))
            # A browse session on the same authenticated SSH connection must
            # remain usable while the transfer worker is paused mid-copy.
            browser = RemoteFiles(client.open_sftp())
            browser.sftp.get_channel().settimeout(3)
            assert browser.sftp.get_channel() != remote.sftp.get_channel()
            paused, resume = threading.Event(), threading.Event()
            errors = []
            def slow_progress(done, total):
                if done and not paused.is_set():
                    paused.set()
                    if not resume.wait(5):
                        raise RuntimeError('concurrent browse did not finish')
            def copy():
                try:
                    transfer(local, remote, str(source), '/', event, slow_progress, lambda _: 'overwrite')
                except Exception as error:
                    errors.append(error)
            thread = threading.Thread(target=copy)
            thread.start()
            try:
                assert paused.wait(5)
                assert any(name == source.name for name, _ in browser.listing('/'))
                assert browser.listing('/' + source.name)
            finally:
                resume.set()
                thread.join(8)
                browser.sftp.close()
            assert not thread.is_alive() and not errors, errors
            output = root / 'output'
            output.mkdir()
            transfer(remote, local, '/' + source.name, str(output), event, lambda *_: None)
            assert (output / source.name / '子目录' / '中文 空格.bin').read_bytes() == payload
            single = source / 'empty.txt'
            single.write_bytes(b'original')
            transfer(local, remote, str(single), '/', event, lambda *_: None)
            single.write_bytes(b'changed')
            transfer(local, remote, str(single), '/', event, lambda *_: None, lambda _: 'skip')
            assert (remote_root / 'empty.txt').read_bytes() == b'original'
            transfer(local, remote, str(single), '/', event, lambda *_: None, lambda _: 'rename')
            assert (remote_root / 'empty (1).txt').read_bytes() == b'changed'
            transfer(local, remote, str(single), '/', event, lambda *_: None, lambda _: 'overwrite')
            assert (remote_root / 'empty.txt').read_bytes() == b'changed'
            # Cancel after first chunk: preserve original target and clean partial file.
            single.write_bytes(payload)
            def cancel(n, total):
                if n: event.set()
            try: transfer(local, remote, str(single), '/', event, cancel, lambda _: 'overwrite')
            except Cancelled: pass
            else: raise AssertionError('cancel ignored')
            assert (remote_root / 'empty.txt').read_bytes() == b'changed'
            assert not list(remote_root.glob('*.part'))
            event.clear()
            transfer(local, remote, str(single), '/', event, lambda *_: None, lambda _: 'overwrite')
            assert (remote_root / 'empty.txt').read_bytes() == payload
            (source / 'link').symlink_to(single)
            try: transfer(local, remote, str(source / 'link'), '/', event, lambda *_: None)
            except ValueError: pass
            else: raise AssertionError('symlink accepted')
            client.close()
            client, _ = connect('127.0.0.1', port, 'test', 'fixture', lambda *_: False, known)
            client.close()
            key[0] = paramiko.RSAKey.generate(2048)
            try: connect('127.0.0.1', port, 'test', 'fixture', approve, known)
            except paramiko.BadHostKeyException: pass
            else: raise AssertionError('changed host key accepted')
            try: connect('127.0.0.1', port, 'test', 'fixture', lambda *_: False, root / 'unknown')
            except Cancelled: pass
            else: raise AssertionError('unapproved host key accepted')
            assert ssh_host('[::1]::5901') == '::1' and ssh_host('192.168.1.2:1') == '192.168.1.2'
            print('Real SFTP upload/download, nested/empty folders, names, conflict policies, cancellation, retry and host identity passed')
        finally:
            if client: client.close()
            stopped.set()
            listener.close()
            for transport in transports: transport.close()

if __name__ == '__main__': main()
