#!/usr/bin/env python3
"""Publish bounded PNG/JSON qualification evidence from a selected Actions run.
Uses gh's configured token; never copies raw build logs, profiles or credentials.
"""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def api(path,body=None,check=True):
    command=['gh','api',path]
    temporary=None
    try:
        if body is not None:
            with tempfile.NamedTemporaryFile(mode='w',suffix='.json',delete=False) as stream:json.dump(body,stream);temporary=Path(stream.name)
            command+=['--method','POST' if path.endswith('/git/refs') else 'PUT','--input',str(temporary)]
        result=subprocess.run(command,capture_output=True,text=True,check=check)
        return json.loads(result.stdout) if result.returncode==0 else None
    finally:
        if temporary:temporary.unlink(missing_ok=True)


def main():
    repo=os.environ['GH_REPO'];run=os.environ['PROOF_RUN'];source=Path(os.environ['PROOF_DIRECTORY']).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not run.isdecimal():raise ValueError('Invalid repository/run')
    record=api(f'repos/{repo}/actions/runs/{run}')
    if record['repository']['full_name'].casefold()!=repo.casefold() or record['status']!='completed':raise ValueError('The selected run must be completed in this repository')
    branch='build-proof'
    existing=api(f'repos/{repo}/git/ref/heads/{branch}',check=False)
    if existing is None:
        head=api(f'repos/{repo}/git/ref/heads/main')['object']['sha']
        api(f'repos/{repo}/git/refs',{'ref':'refs/heads/'+branch,'sha':head})
    files=[]
    for path in source.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        if not path.resolve().is_relative_to(source):raise ValueError('Proof path escapes source')
        if path.suffix=='.png':
            if path.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Expected an original PNG capture')
        elif path.name in ('qualification.json','result.json'):json.loads(path.read_text())
        else:continue
        if path.stat().st_size>8*1024*1024:raise ValueError('Proof file is too large')
        files.append(path)
    if len(files)>50 or sum(p.stat().st_size for p in files)>32*1024*1024:raise ValueError('Proof budget exceeded')
    if not files:raise ValueError('No PNG/JSON proof was found')
    summary={'run_id':int(run),'source_sha':record['head_sha'],'workflow':record['name'],'conclusion':record['conclusion'],'url':record['html_url'],'scope':'Original test captures/reports. Failure captures do not establish successful qualification.'}
    generated=source/'build-record.json';generated.write_text(json.dumps(summary,indent=2)+'\n');files.append(generated)
    for file in files:
        relative=file.relative_to(source).as_posix();target='proof/'+run+'/'+relative
        prior=api(f'repos/{repo}/contents/{target}?ref={branch}',check=False)
        body={'message':'Record build proof for run '+run,'branch':branch,'content':base64.b64encode(file.read_bytes()).decode()}
        if prior:body['sha']=prior['sha']
        api(f'repos/{repo}/contents/{target}',body)
        print('Published '+target,flush=True)
    print(f'https://github.com/{repo}/tree/{branch}/proof/{run}')
if __name__=='__main__':main()
