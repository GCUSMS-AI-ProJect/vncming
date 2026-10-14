"""SSH connection and recursive transfers, independent of the GTK interface."""
import base64
import errno
import hashlib
import os
import posixpath
import stat
import uuid
from pathlib import Path
import paramiko


class Cancelled(Exception):
    pass


def ssh_host(address):
    address = address.removeprefix('vnc://').rstrip('/')
    if address.startswith('['):
        return address[1:address.index(']')]
    return address.split(':', 1)[0]


def connect(host, port, username, password, approve_key, known_hosts=None):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    path = Path(known_hosts or Path.home() / '.config/vncming/ssh_known_hosts')
    if path.exists():
        client.load_host_keys(str(path))
    class VerifyKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, ssh, hostname, key):
            fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
            if not approve_key(hostname, fingerprint):
                raise Cancelled('未确认远端身份')
            path.parent.mkdir(parents=True, exist_ok=True)
            ssh.get_host_keys().add(hostname, key.get_name(), key)
            ssh.save_host_keys(str(path))
            path.chmod(0o600)
    client.set_missing_host_key_policy(VerifyKey())
    try:
        client.connect(host, port=port, username=username, password=password or None,
                       timeout=10, auth_timeout=15, banner_timeout=10,
                       allow_agent=True, look_for_keys=True)
        client.get_transport().set_keepalive(20)
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(20)
        return client, RemoteFiles(sftp)
    except Exception:
        client.close()
        raise


class LocalFiles:
    join = staticmethod(os.path.join)
    basename = staticmethod(os.path.basename)
    parent = staticmethod(os.path.dirname)
    def normalize(self, path):
        return os.path.abspath(os.path.expanduser(path))
    def listing(self, path):
        with os.scandir(path) as entries:
            return [(entry.name, entry.stat(follow_symlinks=False)) for entry in entries]
    def info(self, path):
        return os.lstat(path)
    def mkdir(self, path):
        os.mkdir(path)
    def open(self, path, mode):
        return open(path, ('x' if mode == 'wx' else mode) + 'b')
    def remove(self, path):
        os.unlink(path)
    def publish(self, temporary, final, overwrite):
        if overwrite:
            os.replace(temporary, final)
        else:
            os.link(temporary, final)  # atomic refusal if the target appeared meanwhile
            os.unlink(temporary)


class RemoteFiles:
    join = staticmethod(posixpath.join)
    basename = staticmethod(posixpath.basename)
    parent = staticmethod(posixpath.dirname)
    def __init__(self, sftp):
        self.sftp = sftp
    def normalize(self, path):
        return self.sftp.normalize(path)
    def listing(self, path):
        return [(item.filename, item) for item in self.sftp.listdir_attr(path)]
    def info(self, path):
        return self.sftp.lstat(path)
    def mkdir(self, path):
        self.sftp.mkdir(path)
    def open(self, path, mode):
        return self.sftp.open(path, mode)
    def remove(self, path):
        self.sftp.remove(path)
    def publish(self, temporary, final, overwrite):
        if overwrite:
            # Do not delete the existing target if atomic overwrite is unavailable.
            self.sftp.posix_rename(temporary, final)
        else:
            self.sftp.rename(temporary, final)


def exists(files, path):
    try:
        return files.info(path)
    except OSError as error:
        if error.errno == errno.ENOENT:
            return None
        raise


def safe_name(name):
    if name in ('', '.', '..') or '/' in name or '\x00' in name:
        raise ValueError('无效文件名称')
    return name


def transfer(source, destination, source_path, destination_dir, cancelled, progress,
             conflict=lambda path: 'skip'):
    """Plan before copying, preserve empty directories, publish only complete files."""
    def check():
        if cancelled.is_set():
            raise Cancelled('已取消')
    plan = []
    snapshots = {}
    def walk(path, relative):
        check()
        info = source.info(path)
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('暂不传输符号链接：' + path)
        if stat.S_ISDIR(info.st_mode):
            plan.append((path, relative, True, 0))
            for name, _ in sorted(source.listing(path)):
                walk(source.join(path, safe_name(name)), relative + [name])
        elif stat.S_ISREG(info.st_mode):
            snapshots[path] = (info.st_size, info.st_mtime)
            plan.append((path, relative, False, info.st_size))
        else:
            raise ValueError('不支持特殊文件：' + path)
    walk(source_path, [safe_name(source.basename(source_path.rstrip('/')))])
    total = sum(item[3] for item in plan)
    done, skipped = 0, 0
    progress(0, total)
    for path, relative, directory, size in plan:
        check()
        target = destination.join(destination_dir, *relative)
        present = exists(destination, target)
        if present and stat.S_ISLNK(present.st_mode):
            raise ValueError('目标是符号链接，无法写入：' + target)
        if directory:
            if present and not stat.S_ISDIR(present.st_mode):
                raise ValueError('目标已有同名文件：' + target)
            if not present:
                destination.mkdir(target)
            continue
        if present and not stat.S_ISREG(present.st_mode):
            raise ValueError('目标不是普通文件：' + target)
        overwrite = False
        if present:
            action = conflict(target)
            check()
            if action == 'skip':
                done += size
                skipped += 1
                progress(done, total)
                continue
            if action == 'rename':
                stem, suffix = posixpath.splitext(relative[-1])
                index = 1
                while exists(destination, target):
                    target = destination.join(destination.parent(target), f'{stem} ({index}){suffix}')
                    index += 1
            elif action == 'overwrite':
                overwrite = True
            else:
                raise Cancelled('已取消')
        temporary = destination.join(destination.parent(target), '.vncming-' + uuid.uuid4().hex + '.part')
        try:
            with source.open(path, 'r') as reader, destination.open(temporary, 'wx') as writer:
                copied = 0
                while True:
                    check()
                    chunk = reader.read(128 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
                    copied += len(chunk)
                    progress(done + copied, total)
                if copied != size:
                    raise IOError('源文件在传输期间发生变化，请重试')
                current = source.info(path)
                if (current.st_size, current.st_mtime) != snapshots[path]:
                    raise IOError('源文件在传输期间发生变化，请重试')
            check()
            destination.publish(temporary, target, overwrite)
        finally:
            if exists(destination, temporary):
                destination.remove(temporary)
        done += size
    return skipped
