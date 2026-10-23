#!/usr/bin/env python3
"""Exercise the real packaged editor CLI and native window in a private profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import tempfile
import time


def stop_profile_processes(root):
    """Stop only this test's processes, including detached Electron children."""
    import psutil
    prefix = str(root) + '/'
    for attempt in range(3):
        owned = []
        for process in psutil.process_iter(['pid', 'cmdline', 'uids']):
            try:
                if process.info['uids'].real != os.getuid(): continue
                if any(arg.startswith(prefix) for arg in (process.info['cmdline'] or [])):
                    owned.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied): continue
        if not owned: return
        for process in owned:
            try: process.terminate()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(owned, timeout=5)
        for process in alive:
            try: process.kill()
            except psutil.NoSuchProcess: pass
        psutil.wait_procs(alive, timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);out=args.output.resolve()
    with tempfile.TemporaryDirectory(prefix='livara-code-runtime-') as folder:
        root=Path(folder)
        with tarfile.open(args.archive) as archive:archive.extractall(root,filter='data')
        app=root/'livara-code';binary=app/'bin/livara-code'
        version=subprocess.check_output([str(binary),'--version'],text=True,timeout=60).strip()
        product=json.loads((app/'resources/app/product.json').read_text())
        if product['nameShort']!='Livara Code':raise RuntimeError('Unexpected editor branding')
        fixture=root/'Livara-test.txt';fixture.write_text('Livara Code native runtime test\nPersian: سلام لیوارا\n')
        # Install a narrow AppArmor user-namespace allowance on this disposable
        # runner, matching the installed OS's per-application policy.
        if Path('/etc/apparmor.d').is_dir() and Path('/sys/module/apparmor').exists():
            policy=root/'livara-ci-code';policy.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile livara-ci-code '+str(app/'livara-code')+' flags=(unconfined) {\n  userns,\n}\n')
            subprocess.run(['sudo','apparmor_parser','-r',str(policy)],check=True)
        display=':97'
        with (out/'native.log').open('w') as log:
            xvfb=subprocess.Popen(['Xvfb',display,'-screen','0','1280x900x24','-nolisten','tcp'],stdout=log,stderr=subprocess.STDOUT)
            process=None
            try:
                time.sleep(1);env={**os.environ,'DISPLAY':display}
                command=[str(binary),'--user-data-dir',str(root/'profile'),'--extensions-dir',str(root/'extensions'),'--skip-welcome','--skip-release-notes',str(fixture)]
                process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+120;windows=''
                while time.monotonic()<deadline:
                    probe=subprocess.run(['xdotool','search','--onlyvisible','--name','Livara'],env=env,capture_output=True,text=True)
                    if probe.returncode==0 and probe.stdout.strip():windows=probe.stdout.strip();break
                    time.sleep(1)
                if not windows:raise RuntimeError('Packaged editor did not create a visible Livara window in 120 seconds')
                time.sleep(4)
                from PIL import ImageGrab
                ImageGrab.grab(xdisplay=display).save(out/'livara-code-native.png')
                report={'version':version,'product':product['nameShort'],'visible_window':True,'sandbox_disabled':False,'context':'Real source-built editor under Xvfb, private profile and fixture document. CLI and visible-window test; full interaction tests are separate.'}
                (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
            finally:
                if process:
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        process.wait()
                stop_profile_processes(root)
                xvfb.terminate();xvfb.wait(timeout=10)
    return 0
if __name__=='__main__':raise SystemExit(main())
