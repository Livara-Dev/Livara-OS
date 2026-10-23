#!/usr/bin/env python3
"""Test compiled Livara chrome using Gecko's Marionette protocol and X11.
Only a disposable profile enables automation; the shipping preferences and
browser sandbox are unchanged. Captures contain the real native browser UI.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tarfile
import tempfile
import time


class Marionette:
    def __init__(self, port):
        self.socket=socket.create_connection(('127.0.0.1',port),timeout=10);self.socket.settimeout(30);self.sequence=0;self.receive()
    def receive(self):
        length=b''
        while True:
            byte=self.socket.recv(1)
            if not byte:raise RuntimeError('Marionette connection closed')
            if byte==b':':break
            length+=byte
            if len(length)>10:raise RuntimeError('Invalid Marionette frame')
        size=int(length)
        if not 1<=size<=32*1024*1024:raise RuntimeError('Oversized Marionette frame')
        payload=bytearray()
        while len(payload)<size:
            block=self.socket.recv(size-len(payload))
            if not block:raise RuntimeError('Incomplete Marionette frame')
            payload.extend(block)
        return json.loads(payload)
    def call(self,name,values=None):
        self.sequence+=1;payload=json.dumps([0,self.sequence,name,values or {}]).encode()
        self.socket.sendall(str(len(payload)).encode()+b':'+payload)
        while True:
            result=self.receive()
            if isinstance(result,list) and result[:2]==[1,self.sequence]:break
        if result[2]:raise RuntimeError(name+': '+json.dumps(result[2]))
        return result[3]
    def script(self,script):
        value=self.call('WebDriver:ExecuteScript',{'script':script,'args':[],'newSandbox':False,'sandbox':'default','line':1,'filename':'livara-runtime-test'})
        return value.get('value',value) if isinstance(value,dict) else value
    def context(self,value):self.call('Marionette:SetContext',{'value':value})
    def close(self):self.socket.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);out=args.output.resolve()
    checks={};client=None;browser=None;display=None;wm=None
    with tempfile.TemporaryDirectory(prefix='livara-browser-chrome-') as folder:
        root=Path(folder)
        with tarfile.open(args.archive) as archive:archive.extractall(root,filter='data')
        binary=root/'livara-browser/livara-browser'
        version=subprocess.check_output([str(binary),'--version'],text=True,timeout=30).strip()
        if 'Livara' not in version or 'Zen' in version:raise RuntimeError('Compiled branding failed: '+version)
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        profile=root/'profile';profile.mkdir();(profile/'user.js').write_text(f'user_pref("marionette.port", {port});\nuser_pref("browser.shell.checkDefaultBrowser", false);\n')
        with (out/'browser-chrome.log').open('w') as log:
            try:
                display=subprocess.Popen(['Xvfb',':96','-screen','0','1280x900x24','-nolisten','tcp'],stdout=log,stderr=subprocess.STDOUT);time.sleep(1)
                env={**os.environ,'DISPLAY':':96'}
                wm=subprocess.Popen(['openbox'],env=env,stdout=log,stderr=subprocess.STDOUT)
                browser=subprocess.Popen([str(binary),'--no-remote','--marionette','--remote-allow-system-access','--profile',str(profile),'about:blank'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+120
                while True:
                    if browser.poll() is not None:raise RuntimeError('Browser exited before Marionette startup')
                    try:client=Marionette(port);break
                    except (OSError,RuntimeError):
                        if time.monotonic()>deadline:raise RuntimeError('Browser automation did not become ready')
                        time.sleep(1)
                client.call('WebDriver:NewSession',{'capabilities':{'alwaysMatch':{}}});client.context('chrome')
                deadline=time.monotonic()+45
                while True:
                    chrome=client.script('return {ui:typeof (window.wrappedJSObject || window).LivaraUI, button:!!document.getElementById("livara-style-button"), controls:document.querySelectorAll("#livara-window-controls button").length, glass:document.documentElement.getAttribute("livara-glass")};')
                    if chrome.get('ui')=='object' and chrome.get('button') and chrome.get('controls')==3:break
                    if time.monotonic()>deadline:raise RuntimeError('Livara chrome did not initialize: '+json.dumps(chrome))
                    time.sleep(1)
                checks['compiled_chrome_initialized']=chrome
                checks['onion_dns_locked']=client.script('return Services.prefs.getBoolPref("network.dns.blockDotOnion") && Services.prefs.prefIsLocked("network.dns.blockDotOnion");')
                if not checks['onion_dns_locked']:raise RuntimeError('Normal browser onion DNS policy is not locked')
                client.script('Services.prefs.setIntPref("browser.livara.radius", 26); Services.prefs.setBoolPref("browser.livara.reduced-motion", true); return true;')
                time.sleep(.3)
                checks['appearance_readback']=client.script('return {radius:document.documentElement.style.getPropertyValue("--livara-radius"),motion:document.documentElement.getAttribute("livara-reduced-motion")};')
                if checks['appearance_readback']!={'radius':'26px','motion':'true'}:raise RuntimeError('Appearance controls did not apply: '+json.dumps(checks['appearance_readback']))
                # Exercise the actual New Tab action, which uses AboutNewTab's
                # configured replacement; typing about:newtab is a different path.
                handles=client.call('WebDriver:GetWindowHandles')
                before=set(handles.get('value',handles) if isinstance(handles,dict) else handles)
                client.script('document.getElementById("cmd_newNavigatorTab").doCommand(); return true;')
                deadline=time.monotonic()+20
                while True:
                    handles=client.call('WebDriver:GetWindowHandles')
                    values=handles.get('value',handles) if isinstance(handles,dict) else handles
                    created=set(values)-before
                    if created:break
                    if time.monotonic()>deadline:raise RuntimeError('New Tab action did not create a tab')
                    time.sleep(.2)
                client.call('WebDriver:SwitchToWindow',{'handle':created.pop()})
                client.context('content');time.sleep(2)
                checks['new_tab']=client.script('return {title:document.title,uri:document.documentURI,dashboard:!!document.getElementById("dashboard"),notes:!!document.getElementById("notes")};')
                if checks['new_tab']['title']!='Livara · Start' or not checks['new_tab']['dashboard'] or not checks['new_tab']['notes']:raise RuntimeError('Livara new-tab dashboard did not render: '+json.dumps(checks['new_tab']))
                client.script('const note=document.getElementById("notes"); note.value="سلام لیوارا — native test"; note.dispatchEvent(new window.Event("input",{bubbles:true})); return true;')
                time.sleep(1)
                checks['notes_saved']=client.script('return document.getElementById("notes-state").textContent;')
                if checks['notes_saved']!='SAVED LOCALLY':raise RuntimeError('Normal-profile notes were not saved: '+checks['notes_saved'])
                client.call('WebDriver:Refresh');time.sleep(1)
                checks['notes_persisted']=client.script('return document.getElementById("notes").value;')
                if checks['notes_persisted']!='سلام لیوارا — native test':raise RuntimeError('Dashboard notes did not persist after reload')
                client.script('document.getElementById("timer-toggle").click(); return true;');time.sleep(.3)
                checks['focus_started']=client.script('return document.getElementById("timer-toggle").textContent;')
                if checks['focus_started']!='Pause focus':raise RuntimeError('Focus timer did not start')
                client.script('document.getElementById("timer-toggle").click(); return true;')
                from PIL import ImageGrab
                ImageGrab.grab(xdisplay=':96').save(out/'livara-browser-dashboard.png')
                client.context('chrome');client.script('(window.wrappedJSObject || window).LivaraUI.openPanel(); return true;');time.sleep(1)
                checks['appearance_panel']=client.script('return !!document.querySelector(".livara-panel") && !!document.querySelector(".livara-tor-launch");')
                if not checks['appearance_panel']:raise RuntimeError('Livara appearance/Tor control panel did not render')
                ImageGrab.grab(xdisplay=':96').save(out/'livara-browser-appearance.png')
                report={'version':version,'checks':checks,'sandbox_disabled':False,'automation':'Marionette enabled only in this private test profile','context':'Actual compiled native browser with Openbox/Xvfb. No Tor circuit or physical hardware claim.'}
                (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
            finally:
                if client:client.close()
                if browser:
                    try:os.killpg(browser.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:browser.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(browser.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        browser.wait()
                from importlib.util import spec_from_file_location,module_from_spec
                spec=spec_from_file_location('code_cleanup',Path(__file__).with_name('code-runtime-smoke.py'));module=module_from_spec(spec);spec.loader.exec_module(module);module.stop_profile_processes(root)
                for process in (wm,display):
                    if process:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
    return 0
if __name__=='__main__':raise SystemExit(main())
