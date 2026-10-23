#!/usr/bin/env python3
"""Check Mozilla compiler access early and cache its pinned provenance/archive.

Only official Mozilla endpoints are used, with TLS and SHA-256 checks enabled.
The source patch uses the verified local provenance for this one pinned task;
all other tasks and Mozilla's archive checksum verification remain unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
QUEUE = 'https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/'
DIRECT = 'https://firefoxci.taskcluster-artifacts.net/'
ANCHOR = '                cot = cache._download_manager.session.get(cot_url)'
MARKER = '# Livara: pinned, checksum-verified local Mozilla provenance.'


def manifest():
    item = json.loads((HERE/'toolchains.json').read_text())
    upstream = json.loads((HERE/'upstream.json').read_text())
    if item.get('schema') != 1 or item.get('firefox') != upstream['firefox']['version']:
        raise ValueError('Review Mozilla compiler pins for this Firefox release')
    if not re.fullmatch(r'[A-Za-z0-9_-]{22}', item.get('task_id', '')) or item.get('artifact') != 'public/build/clang.tar.zst':
        raise ValueError('Invalid pinned Mozilla toolchain')
    for key in ('sha256', 'chain_of_trust_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', item.get(key, '')): raise ValueError('Invalid toolchain checksum')
    if not isinstance(item.get('size'), int) or not 1 <= item['size'] <= 2*1024**3: raise ValueError('Invalid toolchain size')
    return item


def urls(item, artifact):
    return [QUEUE+item['task_id']+'/artifacts/'+artifact, DIRECT+item['task_id']+'/0/'+artifact]


def context():
    result = ssl.create_default_context()
    for key in ('LIVARA_BUILD_CA', 'SSL_CERT_FILE'):
        if os.environ.get(key): result.load_verify_locations(cafile=os.environ[key])
    return result


def fetch_small(url, limit, probe=False):
    request = urllib.request.Request(url, headers={'Range':'bytes=0-0'} if probe else {})
    with urllib.request.urlopen(request, timeout=20, context=context()) as response:
        if response.status not in (200, 206): raise ValueError('Unexpected Mozilla HTTP response')
        data = response.read(1 if probe else limit+1)
        if not data or len(data)>limit: raise ValueError('Invalid Mozilla response size')
        return data


def request_official(candidates, limit, probe=False, fetch=fetch_small):
    errors=[]
    for attempt in range(2):
        for url in candidates:
            try: return fetch(url, limit, probe)
            except (OSError, ValueError, urllib.error.URLError) as error:
                # Print no redirect query strings, proxy credentials or response bodies.
                status = getattr(error, 'code', None)
                errors.append(str(status) if status else type(error).__name__)
        if attempt==0: time.sleep(1)
    raise RuntimeError('Mozilla compiler access failed ('+', '.join(errors)+'). '
        'Build stopped before source downloads/compilation. Check access to '
        'firefox-ci-tc.services.mozilla.com and firefoxci.taskcluster-artifacts.net '
        'from Docker Desktop. TLS and checksum checks were not disabled. Keep Docker caches.')


def verify_cot(data, item):
    if hashlib.sha256(data).hexdigest()!=item['chain_of_trust_sha256']:
        raise ValueError('Mozilla provenance checksum mismatch; refusing compiler')
    value=json.loads(data)
    if value.get('taskId')!=item['task_id'] or value.get('artifacts',{}).get(item['artifact'],{}).get('sha256')!=item['sha256']:
        raise ValueError('Mozilla provenance does not match pinned compiler')
    return value


def preflight(item):
    print('Checking pinned Mozilla compiler provenance and archive access before long builds...', flush=True)
    data=request_official(urls(item, 'public/chain-of-trust.json'), 1024*1024)
    verify_cot(data, item)
    request_official(urls(item, item['artifact']), 1, probe=True)
    print('Mozilla compiler access and pinned provenance checks passed.', flush=True)
    return data


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def cached_paths(state, item):
    url=urls(item,item['artifact'])[0]
    archive=state/'toolchains'/(hashlib.sha256(url.encode()).hexdigest()[:16]+'-clang.tar.zst')
    cot=state/'livara-toolchains'/('cot-'+item['task_id']+'.json')
    return archive,cot


def prepare(state, item, run=subprocess.run):
    if not state.is_absolute() or state==Path('/') or state.is_symlink(): raise ValueError('Use a dedicated absolute Mozilla cache')
    archive,cot=cached_paths(state,item)
    if archive.is_symlink() or cot.is_symlink(): raise ValueError('Toolchain cache files cannot be symlinks')
    archive.parent.mkdir(parents=True,exist_ok=True);cot.parent.mkdir(parents=True,exist_ok=True)
    if cot.is_file(): verify_cot(cot.read_bytes(),item)
    if archive.is_file() and archive.stat().st_size==item['size'] and digest(archive)==item['sha256'] and cot.is_file():
        print('Using checksum-verified cached Mozilla compiler and provenance.',flush=True);return
    provenance=preflight(item)
    cot.write_bytes(provenance)
    with tempfile.NamedTemporaryFile(prefix='.livara-clang-',dir=archive.parent,delete=False) as stream: temporary=Path(stream.name)
    try:
        for url in urls(item,item['artifact']):
            try:
                print('Downloading the pinned Mozilla compiler before source preparation...',flush=True)
                run(['curl','--fail','--location','--show-error','--retry','2','--retry-all-errors',
                     '--connect-timeout','20','--max-time','900','--retry-max-time','1000',
                     '--proto','=https','--proto-redir','=https','--output',str(temporary),url],check=True)
                if temporary.stat().st_size!=item['size'] or digest(temporary)!=item['sha256']:
                    raise ValueError('Compiler archive checksum/size mismatch')
                temporary.replace(archive);print('Mozilla compiler cached and SHA-256 verified.',flush=True);return
            except subprocess.CalledProcessError: continue
        raise RuntimeError('Mozilla compiler download failed before source preparation; keep Docker caches and check network access')
    finally: temporary.unlink(missing_ok=True)


def patch(engine, item):
    path=engine/'python/mozbuild/mozbuild/artifact_commands.py';text=path.read_text()
    replacement='\n'.join([
        '                '+MARKER,
        f'                if task_id == {item["task_id"]!r}:',
        '                    state = pathlib.Path(os.environ["MOZBUILD_STATE_PATH"])',
        f'                    local_cot = state / "livara-toolchains" / {("cot-"+item["task_id"]+".json")!r}',
        '                    raw_cot = local_cot.read_bytes()',
        f'                    if hashlib.sha256(raw_cot).hexdigest() != {item["chain_of_trust_sha256"]!r}:',
        '                        raise ValueError("Livara Mozilla provenance checksum mismatch")',
        '                    cot = requests.Response()',
        '                    cot.status_code = 200',
        '                    cot._content = raw_cot',
        '                else:',
        '    '+ANCHOR,
    ])
    if MARKER in text:
        if text.count(replacement)!=1: raise ValueError('Inconsistent Mozilla provenance cache patch')
        return
    if text.count(ANCHOR)!=1: raise ValueError('Mozilla artifact downloader changed; review the provenance cache integration')
    path.write_text(text.replace(ANCHOR,replacement))
    print('Integrated verified local provenance for the pinned Mozilla compiler only.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Check network and provenance without downloading the 453 MB compiler')
    parser.add_argument('--state',type=Path)
    parser.add_argument('--engine',type=Path)
    args=parser.parse_args();item=manifest()
    if args.check: preflight(item)
    else:
        if not args.state: parser.error('--state is required when caching')
        prepare(args.state,item)
        if args.engine: patch(args.engine,item)
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,RuntimeError) as error: raise SystemExit(str(error))
