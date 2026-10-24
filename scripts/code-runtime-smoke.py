#!/usr/bin/env python3
"""Exercise the real packaged editor CLI and native window in a private profile."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tarfile
import tempfile
import time


# Node 24 provides fetch and WebSocket, so the probe needs no npm package or
# injected workbench script. CDP is exposed only on a private loopback port for
# this disposable profile; normal users never launch Code with this switch.
CONTROLS_PROBE = r'''
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
const [port, windowId] = process.argv.slice(1);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(check, label) {
    for (let i = 0; i < 120; i++) {
        const result = await check();
        if (result) { return result; }
        await pause(100);
    }
    throw new Error(`Timed out: ${label}`);
}
const targets = await waitFor(async () => {
    try {
        const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        return list.find(target => target.type === 'page' && target.url.includes('workbench'));
    } catch { return false; }
}, 'Electron workbench debugging target');
const socket = new WebSocket(targets.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
});
let sequence = 0;
const pending = new Map();
socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    const request = pending.get(message.id);
    if (!request) { return; }
    pending.delete(message.id);
    clearTimeout(request.timer);
    if (message.error) { request.reject(new Error(JSON.stringify(message.error))); }
    else { request.resolve(message.result); }
});
function send(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            pending.delete(id); reject(new Error(`CDP command timed out: ${method}`));
        }, 15000);
        pending.set(id, { resolve, reject, timer });
        socket.send(JSON.stringify({ id, method, params }));
    });
}
async function evaluate(expression) {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) { throw new Error(JSON.stringify(result.exceptionDetails)); }
    return result.result.value;
}
function state() { return execFileSync('xprop', ['-id', windowId, '_NET_WM_STATE'], { encoding: 'utf8' }); }
const fullscreen = () => state().includes('_NET_WM_STATE_FULLSCREEN');
const maximized = () => state().includes('_NET_WM_STATE_MAXIMIZED_VERT') && state().includes('_NET_WM_STATE_MAXIMIZED_HORZ');
function key(name) { execFileSync('xdotool', ['windowactivate', '--sync', windowId, 'key', '--clearmodifiers', name]); }
const checks = [];
try {
    await send('Runtime.enable');
    const defaults = await waitFor(() => evaluate(`(() => {
        const root = document.documentElement;
        const group = document.querySelector('.part.titlebar .window-controls-container:not(.wco-enabled)');
        if (!root.classList.contains('livara-traffic-lights') || !group) return null;
        const buttons = ['close', 'minimize', 'max-restore'].map(name => group.querySelector('.window-' + name));
        if (buttons.some(button => !button || button.getBoundingClientRect().width < 1)) return null;
        return { order: buttons.map(button => button.getBoundingClientRect().x),
            roles: buttons.map(button => button.getAttribute('role')),
            labels: buttons.map(button => button.getAttribute('aria-label')),
            diameter: getComputedStyle(buttons[0], '::after').width,
            hitWidth: buttons[0].getBoundingClientRect().width,
            color: getComputedStyle(buttons[0], '::after').backgroundColor };
    })()`), 'visible compiled traffic-light controls');
    assert(defaults.order[0] < defaults.order[1] && defaults.order[1] < defaults.order[2], 'close/minimize/green order');
    assert.deepEqual(defaults.roles, ['button', 'button', 'button']);
    assert(defaults.labels.every(Boolean), 'all buttons have accessible labels');
    assert.equal(defaults.diameter, '14px');
    assert.equal(defaults.color, 'rgb(255, 95, 87)');
    assert(defaults.hitWidth >= 28, 'pointer target retains larger width');
    checks.push('visible traffic lights, order, colors, diameter, target size and accessible labels');
    if (maximized()) { key('alt+F10'); await waitFor(() => !maximized(), 'normalize initial window state'); }
    await evaluate(`document.querySelector('.window-controls-container .window-max-restore').click()`);
    await waitFor(fullscreen, 'green enters real native fullscreen');
    key('F11'); await waitFor(() => !fullscreen(), 'F11 exits real native fullscreen');
    checks.push('green native fullscreen and F11 exit');

    // Replace the DOM group with fresh nodes as workbench titlebar recreation
    // does. The clone deliberately lacks Livara's labels, focus and event
    // listeners. A one-shot controller cannot pass this check.
    await evaluate(`(() => {
        const original = document.querySelector('.part.titlebar .window-controls-container:not(.wco-enabled)');
        const replacement = original.cloneNode(true);
        for (const button of replacement.querySelectorAll('.window-icon')) {
            button.removeAttribute('role'); button.removeAttribute('aria-label'); button.removeAttribute('tabindex');
        }
        window.__livaraSmokeControls = { original, replacement };
        original.replaceWith(replacement);
    })()`);
    await waitFor(() => evaluate(`(() => {
        const group = window.__livaraSmokeControls.replacement;
        const green = group.querySelector('.window-max-restore');
        return green.getAttribute('aria-label') === 'Toggle full screen' && green.tabIndex === 0;
    })()`), 'new controls receive live labels and keyboard focus');
    await evaluate(`window.__livaraSmokeControls.replacement.querySelector('.window-max-restore').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))`);
    await waitFor(fullscreen, 'recreated green activates real fullscreen by keyboard');
    key('F11'); await waitFor(() => !fullscreen(), 'exit recreated-control fullscreen');
    checks.push('recreated controls rebind automatically, including keyboard fullscreen');

    await evaluate(`(() => { const { original, replacement } = window.__livaraSmokeControls; replacement.replaceWith(original); })()`);
    await pause(200);
    await evaluate(`window.__livaraSmokeControls.original.querySelector('.window-max-restore').dispatchEvent(
        new MouseEvent('click', { bubbles: true, cancelable: true, shiftKey: true }))`);
    await waitFor(maximized, 'Shift-green native maximize');
    await evaluate(`window.__livaraSmokeControls.original.querySelector('.window-max-restore').dispatchEvent(
        new MouseEvent('click', { bubbles: true, cancelable: true, shiftKey: true }))`);
    await waitFor(() => !maximized(), 'Shift-green native restore');
    checks.push('original native maximize/restore actions survive controller refresh');
    await evaluate(`window.__livaraSmokeControls.original.querySelector('.window-minimize').click()`);
    await waitFor(() => execFileSync('xprop', ['-id', windowId, 'WM_STATE'], { encoding: 'utf8' }).includes('Iconic'), 'native minimize');
    execFileSync('xdotool', ['windowmap', windowId, 'windowactivate', '--sync', windowId]);
    await waitFor(() => execFileSync('xprop', ['-id', windowId, 'WM_STATE'], { encoding: 'utf8' }).includes('Normal'), 'restore minimized window');
    checks.push('native minimize and window-manager restore');
    console.log(JSON.stringify({ passed: true, defaults, checks }));
} finally {
    try {
        await evaluate(`(() => { const state = window.__livaraSmokeControls; if (state?.replacement.isConnected) state.replacement.replaceWith(state.original); delete window.__livaraSmokeControls; })()`);
    } finally { socket.close(); }
}
'''


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
    (out/'qualification.json').unlink(missing_ok=True)
    subprocess.run(['node', '--input-type=module', '-e',
                    "if (typeof WebSocket !== 'function' || typeof fetch !== 'function') throw new Error('Node 24 is required for Code controls validation')"], check=True)
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
            manager=None
            try:
                time.sleep(1);env={**os.environ,'DISPLAY':display}
                manager=subprocess.Popen(['openbox','--sm-disable'],env=env,stdout=log,stderr=subprocess.STDOUT)
                wm_deadline=time.monotonic()+20
                while time.monotonic()<wm_deadline:
                    wm=subprocess.run(['xprop','-root','_NET_SUPPORTING_WM_CHECK'],env=env,capture_output=True,text=True)
                    if wm.returncode==0 and 'window id #' in wm.stdout:break
                    if manager.poll() is not None:raise RuntimeError('Private Openbox window manager exited')
                    time.sleep(.2)
                else:raise RuntimeError('Private window manager did not become ready')
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1',0))
                    debugging_port=listener.getsockname()[1]
                command=[str(binary),'--user-data-dir',str(root/'profile'),'--extensions-dir',str(root/'extensions'),
                         '--remote-debugging-address=127.0.0.1',f'--remote-debugging-port={debugging_port}',
                         '--skip-welcome','--skip-release-notes',str(fixture)]
                process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+120;windows=''
                while time.monotonic()<deadline:
                    probe=subprocess.run(['xdotool','search','--onlyvisible','--name','Livara'],env=env,capture_output=True,text=True)
                    if probe.returncode==0 and probe.stdout.strip():windows=probe.stdout.strip();break
                    time.sleep(1)
                if not windows:raise RuntimeError('Packaged editor did not create a visible Livara window in 120 seconds')
                window_id=windows.splitlines()[0]
                probe=subprocess.run(['node','--input-type=module','-e',CONTROLS_PROBE,str(debugging_port),window_id],
                                     env=env,capture_output=True,text=True,timeout=150)
                (out/'controls-probe.log').write_text(probe.stdout+probe.stderr)
                if probe.returncode:
                    raise RuntimeError('Compiled window controls failed behavioral validation; see controls-probe.log')
                controls=json.loads(probe.stdout)
                if controls.get('passed') is not True:raise RuntimeError('Controls probe did not report successful checks')
                from PIL import ImageGrab
                ImageGrab.grab(xdisplay=display).save(out/'livara-code-native.png')
                report={'version':version,'product':product['nameShort'],'visible_window':True,'sandbox_disabled':False,
                        'controls':controls,'context':'Real source-built editor under Xvfb and Openbox, private profile and fixture document. Native fullscreen, keyboard, controller recreation, maximize/restore and minimize checks; no full OS rebuild.'}
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
                if manager:
                    manager.terminate()
                    try:manager.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        manager.kill();manager.wait(timeout=5)
                xvfb.terminate();xvfb.wait(timeout=10)
    return 0
if __name__=='__main__':raise SystemExit(main())
