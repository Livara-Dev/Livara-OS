#!/usr/bin/env python3
"""Exercise native menus, pages, persistent preferences and monitor changes.

Uses a disposable Firefox profile, a loopback web server, and real pointer
input. The browser sandbox stays enabled. No personal profile is accessed.
"""
import argparse,os,json,time,subprocess,socket,signal,importlib.util,tempfile,threading,http.server,shutil
from pathlib import Path
from PIL import ImageGrab
spec=importlib.util.spec_from_file_location('chrome',Path(__file__).with_name('browser-chrome-smoke.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('application',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
class Page(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  body=b'<!doctype html><title>Livara browser reliability</title><h1>Loaded normally</h1><a id="link" href="/second">Open this link</a><input id="text" value="copy this text"><canvas id="canvas" width="8" height="8"></canvas><script>localStorage.setItem("reliable","yes");document.getElementById("canvas").getContext("2d").fillRect(0,0,8,8);</script>'
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Page);threading.Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}/'
def dashboard(client):
 client.context('content');result=client.call('WebDriver:GetWindowHandles');before=set(result.get('value',result) if isinstance(result,dict) else result)
 client.context('chrome');client.script('document.getElementById("cmd_newNavigatorTab").doCommand(); return true;')
 client.context('content')
 for attempt in range(30):
  result=client.call('WebDriver:GetWindowHandles');handles=result.get('value',result) if isinstance(result,dict) else result;new=set(handles)-before
  if new:break
  time.sleep(.2)
 else:raise RuntimeError('Actual New Tab command did not create a tab')
 client.call('WebDriver:SwitchToWindow',{'handle':new.pop()})
 for attempt in range(30):
  if client.script('return !!document.getElementById("notes") && document.readyState === "complete";'):break
  time.sleep(.2)
 else:raise RuntimeError('Dashboard failed to initialize')
 return client.script('return {title:document.title,notes:document.getElementById("notes").value,clock:document.getElementById("clock").textContent};')

checks={};binary=(args.application/'livara-browser').resolve()
with tempfile.TemporaryDirectory(prefix='browser-restart-') as folder:
 profile=Path(folder)/'profile';profile.mkdir()
 for phase,resolution in enumerate(('1440x1000','1280x720')):
  probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
  (profile/'user.js').write_text(f'user_pref("marionette.port",{port});\nuser_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("zen.welcome-screen.seen",true);\n')
  log=(out/f'phase-{phase}.log').open('w');env={**os.environ,'DISPLAY':':97'}
  display=subprocess.Popen(['Xvfb',':97','-screen','0',resolution+'x24','-nolisten','tcp'],stdout=log,stderr=subprocess.STDOUT);time.sleep(1)
  wm=subprocess.Popen(['openbox'],env=env,stdout=log,stderr=subprocess.STDOUT) if shutil.which('openbox') else None
  browser=subprocess.Popen([str(binary),'--no-remote','--marionette','--remote-allow-system-access','--profile',str(profile),'about:blank'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  client=None
  try:
   for i in range(90):
    try:client=m.Marionette(port);break
    except (OSError,RuntimeError):time.sleep(1)
   assert client,'browser did not start'
   client.call('WebDriver:NewSession',{'capabilities':{'alwaysMatch':{}}});client.context('chrome');time.sleep(2)
   geom=client.script('return {width:outerWidth,height:outerHeight,x:screenX,y:screenY,availableWidth:screen.availWidth,availableHeight:screen.availHeight,scale:devicePixelRatio,glass:document.documentElement.getAttribute("livara-glass"),appearance:document.documentElement.getAttribute("livara-appearance"),scheme:getComputedStyle(document.documentElement).colorScheme,contrast:matchMedia("(forced-colors: active)").matches,delayed:gBrowserInit.delayedStartupFinished};')
   print('GEOMETRY',phase,json.dumps(geom),flush=True);checks[f'geometry_{resolution}']=geom
   assert geom['width']<=geom['availableWidth']+8 and geom['height']<=geom['availableHeight']+8,geom
   assert geom['contrast'] or geom['scheme']==geom['appearance'],'Selected browser appearance was overridden at startup'
   if phase==0:
    client.context('content');client.call('WebDriver:Navigate',{'url':url});time.sleep(.5)
    page=client.script('return {title:document.title,storage:localStorage.getItem("reliable"),canvas:document.getElementById("canvas").getContext("2d").getImageData(0,0,1,1).data[3]};');assert page['storage']=='yes' and page['canvas']==255;checks['page']=page
    element=client.call('WebDriver:FindElement',{'using':'css selector','value':'#link'});element=element.get('value',element)
    client.call('WebDriver:PerformActions',{'actions':[{'type':'pointer','id':'mouse','parameters':{'pointerType':'mouse'},'actions':[{'type':'pointerMove','duration':0,'origin':element,'x':0,'y':0},{'type':'pointerDown','button':2},{'type':'pointerUp','button':2}]}]});time.sleep(.5);client.context('chrome')
    menu=client.script('let p=document.getElementById("contentAreaContextMenu"),a=document.getElementById("context-openlinkintab");return {state:p.state,label:a.label,rect:p.getBoundingClientRect().toJSON()};');print('MENU',menu,flush=True);assert menu['state']=='open' and menu['label'];checks['right_click']=menu
    ImageGrab.grab(xdisplay=':97').save(out/'right-click.png')
    client.script('document.getElementById("context-openlinkintab").doCommand();document.getElementById("contentAreaContextMenu").hidePopup();return true;');time.sleep(.5);checks['open_link_in_tab']=client.script('return [...gBrowser.browsers].some(b=>b.currentURI.spec.endsWith("/second"));');assert checks['open_link_in_tab']
    client.script('(window.wrappedJSObject || window).LivaraUI.openPanel();return true;');time.sleep(.3)
    settings=client.script('for(const [name,value] of [["appearance","light"],["accent","ocean"],["radius","26"],["font-size","16"]]){let e=document.getElementById("livara-"+name);e.value=value;e.dispatchEvent(new Event("change",{bubbles:true}));}return {appearance:Services.prefs.getStringPref("browser.livara.appearance"),accent:Services.prefs.getStringPref("browser.livara.accent"),radius:Services.prefs.getIntPref("browser.livara.radius"),font:Services.prefs.getIntPref("browser.livara.font-size")};');checks['written_settings']=settings
    assert 'browser.livara.radius' in (profile/'prefs.js').read_text(),'confirmed settings were not flushed to disk'
    client.script('document.getElementById("livara-appearance-panel").hidePopup();window.resizeTo(1380,950);return true;');time.sleep(.5)
    client.context('content');client.call('WebDriver:Navigate',{'url':'about:preferences'});time.sleep(2)
    prefs=client.script('return {uri:document.documentURI,title:document.title,labels:[...document.querySelectorAll("[data-l10n-id]")].map(e=>e.textContent.trim()).filter(Boolean).slice(0,8)};');print('PREFERENCES',prefs,flush=True);assert prefs['labels'];checks['preferences']=prefs
    checks['new_tab']=dashboard(client);assert checks['new_tab']['title']=='Livara · Start'
    client.script('let note=document.getElementById("notes");note.value="Restart proof — سلام";note.dispatchEvent(new Event("input",{bubbles:true}));return true;');time.sleep(.8)
   else:
    saved=client.script('return {appearance:Services.prefs.getStringPref("browser.livara.appearance"),accent:Services.prefs.getStringPref("browser.livara.accent"),radius:Services.prefs.getIntPref("browser.livara.radius"),font:Services.prefs.getIntPref("browser.livara.font-size")};');assert saved==checks['written_settings'],saved;checks['settings_after_full_restart']=saved
    client.context('content');client.call('WebDriver:Navigate',{'url':url});checks['storage_after_restart']=client.script('return localStorage.getItem("reliable");');assert checks['storage_after_restart']=='yes'
    checks['dashboard_after_restart']=dashboard(client);assert checks['dashboard_after_restart']['notes']=='Restart proof — سلام'
    ImageGrab.grab(xdisplay=':97').save(out/'smaller-screen-after-restart.png')
   try:client.call('Marionette:Quit',{'flags':['eAttemptQuit']})
   except (OSError,RuntimeError):pass
   browser.wait(timeout=15)
  finally:
   if client:client.close()
   if browser.poll() is None:
    os.killpg(browser.pid,signal.SIGTERM)
    try:browser.wait(timeout=8)
    except subprocess.TimeoutExpired:os.killpg(browser.pid,signal.SIGKILL);browser.wait()
   if wm:
    wm.terminate();wm.wait(timeout=5)
   display.terminate();display.wait(timeout=5);log.close()
server.shutdown();(out/'verified.json').write_text(json.dumps({'status':'passed','checks':checks},indent=2)+'\n');print(json.dumps(checks,indent=2),flush=True)
