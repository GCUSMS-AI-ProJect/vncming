"""Inspect native authentication titles against a loopback RFB fixture; no keyboard input."""
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import i18n
ROOT = Path(__file__).resolve().parent.parent

for language, title in [('en', 'Authentication — VNCMing'), ('zh_CN', '身份验证 — VNCMing')]:
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(10)
    errors = []
    def serve():
        try:
            with listener.accept()[0] as channel:
                channel.settimeout(10)
                def read(size):
                    data = b''
                    while len(data) < size:
                        block = channel.recv(size - len(data))
                        if not block:
                            raise EOFError()
                        data += block
                    return data
                channel.sendall(b'RFB 003.008\n')
                read(12)
                channel.sendall(b'\x01\x13')
                assert read(1) == b'\x13'
                channel.sendall(b'\x00\x02')
                assert read(2) == b'\x00\x02'
                channel.sendall(b'\x00\x01' + struct.pack('!I', 256))
                assert read(4) == struct.pack('!I', 256)
                channel.sendall(b'\x00\x00\x00\x00')
                read(8)
        except (EOFError, ConnectionError):
            pass
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=serve)
    thread.start()
    i18n.configure(language)
    environment = i18n.native_environment(os.environ, ROOT / 'build/locale')
    process = subprocess.Popen([str(ROOT / 'build/vncviewer/vncviewer'), '-SecurityTypes=Plain',
                                '127.0.0.1::' + str(listener.getsockname()[1])],
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            windows = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
            if '"' + title + '"' in windows:
                break
            assert process.poll() is None, 'Native viewer exited before authentication'
            time.sleep(.05)
        else:
            raise AssertionError('Missing native translated title: ' + title)
    finally:
        process.terminate()
        process.wait(5)
        listener.close()
        thread.join(11)
    assert not errors, errors
print('Native authentication respects both English and Chinese language selections')
