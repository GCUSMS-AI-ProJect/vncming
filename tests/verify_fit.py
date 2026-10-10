import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
"""Verify full-image rendering and mouse coordinates against a local RFB server."""
import json
import re
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

ENGINE = str(Path(__file__).resolve().parent.parent / 'build/vncviewer/vncviewer')

(Path(__file__).resolve().parent.parent / "build/test-results").mkdir(parents=True, exist_ok=True)

def check(fullscreen):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    title = 'VNCMing Fit Test ' + str(port)
    points, errors = [], []
    def serve():
        try:
            with listener.accept()[0] as connection:
                def read(n):
                    data = b''
                    while len(data) < n:
                        part = connection.recv(n - len(data))
                        if not part: raise EOFError()
                        data += part
                    return data
                connection.sendall(b'RFB 003.008\n'); read(12)
                connection.sendall(b'\x01\x01'); read(1)
                connection.sendall(bytes(4)); read(1)
                pf = struct.pack('!BBBBHHHBBB3x', 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
                connection.sendall(struct.pack('!HH',800,600)+pf+struct.pack('!I',len(title))+title.encode())
                colors = [b'\x00\x00\xff\x00', b'\x00\xff\x00\x00', b'\xff\x00\x00\x00', b'\xff\xff\xff\x00']
                pixels = (colors[0]*400+colors[1]*400)*300 + (colors[2]*400+colors[3]*400)*300
                sent = False
                while True:
                    kind = read(1)[0]
                    if kind == 0: read(19)
                    elif kind == 2:
                        read(1); read(4*struct.unpack('!H',read(2))[0])
                    elif kind == 3:
                        read(9)
                        if not sent:
                            connection.sendall(b'\x00\x00\x00\x01'+struct.pack('!HHHHi',0,0,800,600,0)+pixels)
                            sent = True
                    elif kind == 4: read(7)
                    elif kind == 5:
                        mask,x,y = struct.unpack('!BHH',read(5))
                        if mask & 1: points.append((x,y))
                    elif kind == 6:
                        read(3); read(struct.unpack('!I',read(4))[0])
                    else: raise AssertionError(kind)
        except (EOFError, ConnectionError): pass
        except Exception as error: errors.append(repr(error))
        finally: listener.close()
    threading.Thread(target=serve,daemon=True).start()
    args = [ENGINE, '-RemoteResize=0', '-FitToWindow=1', '-geometry=400x300']
    args.append('-FullScreen=' + str(int(fullscreen)))
    log = (Path(__file__).resolve().parent.parent / 'build/test-results/fit-check.log').open('w')
    process = subprocess.Popen(args+['127.0.0.1::'+str(port)],stdout=log,stderr=log)
    try:
        window = None
        for _ in range(100):
            tree = subprocess.run(['xwininfo','-root','-tree'],capture_output=True,text=True).stdout
            for line in tree.splitlines():
                if title in line: window=re.search(r'0x[0-9a-f]+',line)[0]; break
            if window: break
            time.sleep(.05)
        assert window, errors
        time.sleep(2)
        def inspect():
            subprocess.run(['xdotool','windowactivate','--sync',window],check=True)
            time.sleep(.2)
            info=subprocess.run(['xwininfo','-id',window],capture_output=True,text=True).stdout
            def field(name): return int(re.search(name+r':\s+(-?\d+)',info)[1])
            width,height=field('Width'),field('Height')
            root=Gdk.get_default_root_window()
            image=Gdk.pixbuf_get_from_window(root,field('Absolute upper-left X'),field('Absolute upper-left Y'),width,height)
            image.savev(str(Path(__file__).resolve().parent.parent / 'build/test-results/fit-check.png'),'png',[],[])
            data=image.get_pixels();stride=image.get_rowstride();channels=image.get_n_channels()
            # Stay above the desktop input-method indicator at the lower right.
            for x,y,expected in [(20,20,(255,0,0)),(width-20,20,(0,255,0)),(20,height-60,(0,0,255)),(width-100,height-60,(255,255,255))]:
                offset=y*stride+x*channels
                assert tuple(data[offset:offset+3]) == expected, (width,height,x,y,tuple(data[offset:offset+3]))
            subprocess.run(['xdotool','windowactivate','--sync',window,'mousemove','--window',window,str(width//4),str(height//4),'click','1'],check=True)
            time.sleep(.2)
            assert points and abs(points[-1][0]-200)<=2 and abs(points[-1][1]-150)<=2, points
            return width,height
        dimensions=inspect()
        if fullscreen:
            state=subprocess.run(['xprop','-id',window,'_NET_WM_STATE'],capture_output=True,text=True).stdout
            assert '_NET_WM_STATE_FULLSCREEN' in state,state
        else:
            assert dimensions == (400,300),dimensions
            subprocess.run(['xdotool','windowsize',window,'600','450'],check=True)
            time.sleep(.7)
            assert inspect() == (600,450)
        assert not errors,errors
        return {'fullscreen':fullscreen,'dimensions':dimensions,'complete_image':True,'pointer_mapping':True}
    finally:
        process.terminate();process.wait(3)
        log.close()

print(json.dumps([check(False),check(True)]))
