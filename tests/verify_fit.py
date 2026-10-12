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

def check(fullscreen, maximized=False, resize_supported=False, resolution=None, fixed_resolution=None, late_resize_supported=False):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    title = 'VNCMing Fit Test ' + str(port)
    points, errors, resize_requests = [], [], []
    remote_dimensions = [800,600]
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
                advertised = False
                while True:
                    kind = read(1)[0]
                    if kind == 0: read(19)
                    elif kind == 2:
                        read(1); read(4*struct.unpack('!H',read(2))[0])
                    elif kind == 3:
                        read(9)
                        if not sent:
                            extended = b''
                            if resize_supported and not late_resize_supported:
                                extended = struct.pack('!HHHHi',0,0,800,600,-308)
                                extended += b'\x01\x00\x00\x00'+struct.pack('!IHHHHI',0,0,0,800,600,0)
                                advertised = True
                            connection.sendall(struct.pack('!BBH',0,0,2 if extended else 1)+extended+struct.pack('!HHHHi',0,0,800,600,0)+pixels)
                            sent = True
                        elif resize_supported and late_resize_supported and not advertised:
                            extended = struct.pack('!HHHHi',0,0,800,600,-308)
                            extended += b'\x01\x00\x00\x00'+struct.pack('!IHHHHI',0,0,0,800,600,0)
                            connection.sendall(struct.pack('!BBH',0,0,1)+extended)
                            advertised = True
                    elif kind == 4: read(7)
                    elif kind == 5:
                        mask,x,y = struct.unpack('!BHH',read(5))
                        if mask & 1: points.append((x,y))
                    elif kind == 6:
                        read(3); read(struct.unpack('!I',read(4))[0])
                    elif kind == 251:
                        read(1)
                        width,height,screens = struct.unpack('!HHB',read(5))
                        read(1); read(16*screens)
                        resize_requests.append((width,height))
                        remote_dimensions[:] = [width,height]
                        extended = struct.pack('!HHHHi',1,0,width,height,-308)
                        extended += b'\x01\x00\x00\x00'+struct.pack('!IHHHHI',0,0,0,width,height,0)
                        pixels = (colors[0]*(width//2)+colors[1]*(width-width//2))*(height//2)
                        pixels += (colors[2]*(width//2)+colors[3]*(width-width//2))*(height-height//2)
                        connection.sendall(struct.pack('!BBH',0,0,2)+extended+struct.pack('!HHHHi',0,0,width,height,0)+pixels)
                    else: raise AssertionError(kind)
        except (EOFError, ConnectionError): pass
        except Exception as error: errors.append(repr(error))
        finally: listener.close()
    threading.Thread(target=serve,daemon=True).start()
    args = [ENGINE, '-RemoteResize='+str(int(resize_supported)), '-FitToWindow=1', '-geometry=400x300']
    args.append('-FullScreen=' + str(int(fullscreen)))
    args.append('-Maximize=' + str(int(maximized)))
    if resolution:
        args.append('-FullScreenDesktopSize=%dx%d' % resolution)
    if fixed_resolution:
        args.append('-DesktopSize=%dx%d' % fixed_resolution)
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
            assert points and abs(points[-1][0]-remote_dimensions[0]/4)<=2 and abs(points[-1][1]-remote_dimensions[1]/4)<=2, points
            return width,height
        dimensions=inspect()
        if fullscreen:
            state=subprocess.run(['xprop','-id',window,'_NET_WM_STATE'],capture_output=True,text=True).stdout
            assert '_NET_WM_STATE_FULLSCREEN' in state,state
        elif maximized:
            state=subprocess.run(['xprop','-id',window,'_NET_WM_STATE'],capture_output=True,text=True).stdout
            assert '_NET_WM_STATE_FULLSCREEN' not in state,state
            assert '_NET_WM_STATE_MAXIMIZED_VERT' in state,state
            assert '_NET_WM_STATE_MAXIMIZED_HORZ' in state,state
            if fixed_resolution:
                subprocess.run(['xdotool','windowsize',window,'600','450'],check=True)
                time.sleep(1)
                inspect()
        else:
            assert dimensions == (400,300),dimensions
            subprocess.run(['xdotool','windowsize',window,'600','450'],check=True)
            time.sleep(.7)
            assert inspect() == (600,450)
        assert not errors,errors
        if resize_supported and (fullscreen or fixed_resolution):
            target = fixed_resolution or resolution or (1920,1080)
            assert resize_requests and all(size == target for size in resize_requests),resize_requests
            assert tuple(remote_dimensions) == target,remote_dimensions
        return {'fullscreen':fullscreen,'maximized':maximized,'dimensions':dimensions,'remote_dimensions':remote_dimensions,'complete_image':True,'pointer_mapping':True,'resize_requests':resize_requests}
    finally:
        process.terminate();process.wait(3)
        log.close()

print(json.dumps([check(False),check(True),check(False, True),
                  check(True, resize_supported=True),
                  check(True, resize_supported=True, resolution=(1600,900)),
                  check(False, True, resize_supported=True, fixed_resolution=(1920,1080)),
                  check(False, True, resize_supported=True, fixed_resolution=(1920,1080), late_resize_supported=True)]))
