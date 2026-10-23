#!/usr/bin/env python3
"""Prime node-gyp from pinned, verified archives before npm's native builds.

No mirrors, TLS bypass, or unverified node-gyp downloads. The source checkout's
root/build/remote .npmrc targets and host Node version must match the manifest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def validate_manifest(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 8: raise ValueError('Invalid native header manifest')
    seen=set()
    for item in value:
        if not isinstance(item,dict) or set(item)!={'version','url','sha256'}:raise ValueError('Invalid header entry')
        version=item['version']
        if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version) or version in seen:raise ValueError('Invalid/duplicate header version')
        seen.add(version)
        urls=(f'https://nodejs.org/dist/v{version}/node-v{version}-headers.tar.gz',f'https://artifacts.electronjs.org/headers/dist/v{version}/node-v{version}-headers.tar.gz')
        if item['url'] not in urls or not isinstance(item['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('Use pinned official HTTPS header archives')
    return value


def required_versions(source, host_version):
    versions={host_version.removeprefix('v')}
    for directory in ('','build','remote'):
        path=source/directory/'.npmrc';text=path.read_text()
        matches=re.findall(r'^target\s*=\s*[\"\']?(\d+\.\d+\.\d+)[\"\']?\s*$',text,re.M)
        if len(matches)!=1:raise ValueError('Expected one pinned target in '+str(path))
        versions.add(matches[0])
    return versions


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def download(item, folder, run=subprocess.run):
    destination=folder/('node-v'+item['version']+'-headers.tar.gz')
    if destination.is_file() and not destination.is_symlink() and digest(destination)==item['sha256']:return destination
    print('Downloading pinned native headers for '+item['version'],flush=True)
    fd,path=tempfile.mkstemp(prefix='.headers-',suffix='.tar.gz',dir=folder)
    import os
    os.close(fd);temporary=Path(path)
    try:
        run(['curl','--fail','--location','--silent','--show-error','--retry','5','--retry-all-errors',
             '--connect-timeout','30','--max-time','300','--retry-max-time','900','--proto','=https','--proto-redir','=https',
             '--output',str(temporary),item['url']],check=True)
        if digest(temporary)!=item['sha256']:raise ValueError('Header checksum mismatch for '+item['version']+'; npm was not started')
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return destination


def prepare(manifest,source,cache,host_version,gyp,run=subprocess.run):
    entries=validate_manifest(manifest)
    expected=required_versions(source,host_version)
    if {item['version'] for item in entries}!=expected:raise ValueError('Native header manifest does not match root/build/remote/host targets')
    if not cache.is_absolute() or cache==Path('/') or cache.is_symlink():raise ValueError('Use a dedicated absolute node-gyp cache')
    cache.mkdir(parents=True,exist_ok=True)
    archives=cache/'archives';archives.mkdir(exist_ok=True)
    if archives.is_symlink():raise ValueError('Header archive directory cannot be a symbolic link')
    # Verify every archive before invoking node-gyp, so a bad pin cannot produce
    # a mixture of partially prepared targets.
    verified=[(item,download(item,archives,run)) for item in entries]
    for item,archive in verified:
        print('Installing verified local headers for '+item['version'],flush=True)
        run(['node',str(gyp),'install','--target='+item['version'],'--tarball='+str(archive),'--devdir='+str(cache)],check=True)
        if not (cache/item['version']/'include/node/config.gypi').is_file():raise ValueError('node-gyp did not install '+item['version'])
    (cache/'livara-headers.json').write_text(json.dumps(entries,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--gyp',type=Path,default=Path('/usr/local/lib/node_modules/npm/node_modules/node-gyp/bin/node-gyp.js'))
    args=parser.parse_args()
    version=subprocess.check_output(['node','--version'],text=True).strip()
    prepare(json.loads(args.manifest.read_text()),args.source,args.cache,version,args.gyp)
    return 0
if __name__=='__main__':raise SystemExit(main())
