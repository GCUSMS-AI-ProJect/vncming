import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
#!/usr/bin/python3
"""Exercise native authentication and menus against a local RFB fixture."""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time
import gi
gi.require_version('Gdk','3.0')
from gi.repository import Gdk
ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/'build'/'test-results'
OUTPUT.mkdir(parents=True, exist_ok=True)
result={}
server=socket.socket(); server.bind(('127.0.0.1',0));server.listen(1)
port=server.getsockname()[1]
ready=threading.Event()
def serve():
 try:
  s,_=server.accept();s.settimeout(30)
  def read(n):
   b=b''
   while len(b)<n:
    p=s.recv(n-len(b))
    if not p: raise EOFError()
    b+=p
   return b
  s.sendall(b'RFB 003.008\n');read(12)
  s.sendall(b'\x01\x13');assert read(1)==b'\x13'
  s.sendall(b'\x00\x02');assert read(2)==b'\x00\x02'
  s.sendall(b'\x00\x01'+struct.pack('!I',256));assert read(4)==struct.pack('!I',256)
  # Wake the decoder's readiness check without consuming credentials.
  s.sendall(b'\x00\x00\x00\x00')
  u,p=struct.unpack('!II',read(8))
  result['authentication']=read(u)==b'test-user' and read(p)==b'test-password'
  read(1)
  pixel=struct.pack('!BBBBHHHBBB3x',32,24,0,1,255,255,255,16,8,0)
  name=('VNCMing UI Test '+str(port)).encode()
  s.sendall(struct.pack('!HH',800,480)+pixel+struct.pack('!I',len(name))+name)
  ready.set()
  while True:
   kind=read(1)[0]
   if kind==0: read(19)
   elif kind==2:
    read(1);count=struct.unpack('!H',read(2))[0];read(4*count)
   elif kind==3:
    read(9)
    color=bytes([248,246,245,0]);pixels=color*(800*480)
    s.sendall(b'\x00\x00\x00\x01'+struct.pack('!HHHHi',0,0,800,480,0)+pixels)
   elif kind==4: read(7)
   elif kind==5: read(5)
   elif kind==6:
    read(3);n=struct.unpack('!I',read(4))[0];read(n)
   else: raise ValueError(kind)
 except (EOFError, OSError): pass
 except Exception as e:
  result['server_error']=str(e); print('Fixture error:',repr(e),flush=True)
 finally: server.close()
threading.Thread(target=serve,daemon=True).start()
log=(OUTPUT/'ui-check.log').open('w')
proc=subprocess.Popen([str(ROOT/'build/vncviewer/vncviewer'),'-SecurityTypes=Plain','-RemoteResize=0','-FullScreen=0','-Maximize=0','-FitToWindow=0','-Shared=1','127.0.0.1::'+str(port)],stdout=log,stderr=log,env={**os.environ,"XMODIFIERS":"@im=none"})
def find(title):
 import re
 for _ in range(100):
  tree=subprocess.run(['xwininfo','-root','-tree'],capture_output=True,text=True).stdout
  for line in tree.splitlines():
   if '"'+title in line:
    match=re.search(r'0x[0-9a-f]+',line)
    if match:
     pid_info=subprocess.run(['xprop','-id',match.group(),'_NET_WM_PID'],capture_output=True,text=True).stdout
     if not pid_info.strip().endswith('= '+str(proc.pid)): continue
     time.sleep(.3)
     return match.group()
  if proc.poll() is not None: raise RuntimeError('Viewer exited '+str(proc.returncode))
  time.sleep(.1)
 capture('ui-timeout.png')
 raise TimeoutError(title)
def capture(name):
 w=Gdk.get_default_root_window()
 Gdk.pixbuf_get_from_window(w,0,0,w.get_width(),w.get_height()).savev(str(OUTPUT/name),'png',[],[])
def keys(w,*args):
 subprocess.run(['xdotool','windowactivate','--sync',w,'windowfocus','--sync',w,'key',*args],check=True)
try:
 auth=find('身份验证')
 subprocess.run(['xdotool','windowactivate','--sync',auth],check=True)
 time.sleep(.3)
 capture('authentication-preview.png')
 subprocess.run(['xdotool','type','--clearmodifiers','--file','-'],input='test-user',text=True,check=True)
 keys(auth,'Tab')
 subprocess.run(['xdotool','type','--clearmodifiers','--file','-'],input='test-password',text=True,check=True)
 subprocess.run(['xdotool','mousemove','--window',auth,'380','239','click','1'],check=True)
 time.sleep(.5)
 capture('submitted-preview.png')
 assert ready.wait(10),('RFB fixture not initialized',result)
 desktop=find('VNCMing UI Test '+str(port))
 time.sleep(.5)
 subprocess.run(['xdotool','mousemove','--window',desktop,'300','200','click','1'],check=True)
 keys(desktop,'F8')
 time.sleep(.3)
 capture('remote-menu-preview.png')
 import re
 tree=subprocess.run(['xwininfo','-root','-tree'],capture_output=True,text=True).stdout
 menus=[]
 for line in tree.splitlines():
  m=re.search(r'(0x[0-9a-f]+).*?(\d+)x(\d+)\+[0-9]+\+[0-9]+',line)
  if m and 110 <= int(m[2]) <= 180 and 280 <= int(m[3]) <= 340:
   menus.append(m[1])
 assert menus, 'Context menu did not appear'
 subprocess.run(['xdotool','mousemove','--window',menus[0],'60','248','click','1'],check=True)
 options=find('连接选项')
 capture('native-options-preview.png')
 for index, page in enumerate(['compression', 'security', 'input', 'screen', 'misc']):
  subprocess.run(['xdotool','mousemove','--window',options,str(53+86*index),'25','click','1'],check=True)
  time.sleep(.15)
  capture('native-options-'+page+'.png')
  assert proc.poll() is None, 'Viewer exited while switching options pages'
 keys(options,'Escape')
 result['native_options']=True
 result['native_ui']=True
 result['native_process_alive']=proc.poll() is None
finally:
 proc.terminate()
 try: proc.wait(5)
 except subprocess.TimeoutExpired: proc.kill();proc.wait()
 log.close()
(OUTPUT/'ui-check.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
assert result.get('authentication') and result.get('native_ui') and not result.get('server_error'),result
