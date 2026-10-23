#!/usr/bin/env python3
"""Launch the actual compiled browser against a private local HTTP test page.

The page reports DOM, JS, localStorage and pixel rendering results to a loopback
server. The test fails if the packaged executable or engine is absent or if the
browser fails to render the page. Uses a temporary profile, no personal data.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);output=args.output.resolve();result={};received=threading.Event()
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=b'''<!doctype html><meta charset="utf-8"><title>Livara runtime qualification</title><style>body{background:#08040e;color:#d8b4ff;font:24px sans-serif;padding:64px}</style><h1>Livara Browser</h1><p id="status">Testing the compiled engine...</p><script>
            let report={dom:document.querySelector('h1').textContent==='Livara Browser',js:[1,2,3].map(v=>v*2).join(',')==='2,4,6'};
            try{localStorage.setItem('livara-test','passed');report.storage=localStorage.getItem('livara-test')==='passed'}catch(e){report.storage=false}
            let c=document.createElement('canvas');c.width=c.height=8;let ctx=c.getContext('2d');ctx.fillStyle='#b060f0';ctx.fillRect(0,0,8,8);report.canvas=ctx.getImageData(1,1,1,1).data[0]===176;
            document.querySelector('#status').textContent=Object.values(report).every(Boolean)?'DOM, JavaScript, storage and rendering passed.':'A runtime check failed.';
            fetch('/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report)});
            </script>'''
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            length=int(self.headers.get('Content-Length','0'))
            if self.path!='/result' or not 1<=length<=8192:self.send_error(400);return
            try:data=json.loads(self.rfile.read(length))
            except ValueError:self.send_error(400);return
            result.update(data);self.send_response(200);self.end_headers();self.wfile.write(b'ok');received.set()
    with tempfile.TemporaryDirectory(prefix='livara-browser-smoke-') as directory:
        root=Path(directory)
        with tarfile.open(args.archive) as archive:archive.extractall(root,filter='data')
        binary=root/'livara-browser/livara-browser'
        if not binary.is_file() or binary.read_bytes()[:4]!=b'\x7fELF' or not (binary.parent/'libxul.so').is_file():raise RuntimeError('Missing actual compiled browser/engine')
        version=subprocess.check_output([str(binary),'--version'],text=True).strip()
        if 'Livara' not in version or 'Zen' in version:raise RuntimeError('Unexpected product identity: '+version)
        # Firefox requires an existing directory for an explicit --profile.
        profile=root/'profile';profile.mkdir()
        (profile/'user.js').write_text('user_pref("zen.welcome-screen.seen", true);\nuser_pref("browser.shell.checkDefaultBrowser", false);\n')
        # Ubuntu hosted runners restrict user namespaces for unknown binaries.
        # Allow this private test executable; retain the browser's own sandbox.
        if Path('/etc/apparmor.d').is_dir() and Path('/sys/module/apparmor').exists():
            policy=root/'livara-ci-browser'
            policy.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile livara-ci-browser '+str(binary)+'{,-bin} flags=(unconfined) {\n  userns,\n}\n')
            subprocess.run(['sudo','apparmor_parser','-r',str(policy)],check=True)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with (output/'runtime.log').open('w') as log:
                process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1280x900x24',str(binary),'--no-remote','--profile',str(profile),f'http://127.0.0.1:{server.server_port}/'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    deadline=time.monotonic()+120
                    while not received.wait(1):
                        if process.poll() is not None:raise RuntimeError('Compiled browser exited before rendering the test page')
                        if time.monotonic()>=deadline:raise RuntimeError('Compiled browser did not report runtime results within 120 seconds')
                    if result!={'dom':True,'js':True,'storage':True,'canvas':True}:raise RuntimeError('Browser runtime test failed: '+json.dumps(result))
                finally:
                    import signal
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
        finally:server.shutdown();server.server_close()
        report={'version':version,'checks':result,'archive_sha256':hashlib.file_digest(args.archive.open('rb'),'sha256').hexdigest(),'context':'Actual packaged browser under Xvfb, private profile, loopback-only test page; sandbox not disabled.'}
        (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
