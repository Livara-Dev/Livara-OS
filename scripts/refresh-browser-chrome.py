#!/usr/bin/env python3
"""Update Livara JavaScript in an already source-compiled browser package.

The native executable/Gecko engine remain byte-identical. This is a resource
packaging step, not a substitute binary download or another engine compilation.
The source candidate, changed resource hashes and output checksum are recorded.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def update_jar(path,resource):
    suffix='/livara/LivaraUI.js'
    with zipfile.ZipFile(path) as source:
        matches=[n for n in source.namelist() if n.endswith(suffix)]
        if not matches:return None
        if len(matches)!=1:raise ValueError('Ambiguous Livara chrome entry')
        name=matches[0];previous=source.read(name);fresh=resource.read_bytes()
        if previous==fresh:return {'path':name,'before_sha256':hashlib.sha256(previous).hexdigest(),'after_sha256':hashlib.sha256(fresh).hexdigest(),'changed':False}
        staged=path.with_suffix('.livara-update')
        try:
            with zipfile.ZipFile(staged,'w') as output:
                for info in source.infolist():
                    # Generated JS bytecode must be rebuilt from the updated JS.
                    if info.filename.startswith(('jsloader/','jssubloader/')):continue
                    output.writestr(info,fresh if info.filename==name else source.read(info.filename))
            with zipfile.ZipFile(staged) as output:
                if output.testzip() is not None or output.read(name)!=fresh:raise ValueError('Updated browser resource integrity failed')
            os.replace(staged,path)
        finally:staged.unlink(missing_ok=True)
    return {'path':name,'before_sha256':hashlib.sha256(previous).hexdigest(),'after_sha256':hashlib.sha256(fresh).hexdigest(),'changed':True}


def refresh(archive):
    archive=archive.resolve();checksum=Path(str(archive)+'.sha256')
    expected=checksum.read_text().split()
    before=digest(archive)
    if len(expected)!=2 or expected[0]!=before or expected[1]!=archive.name:raise ValueError('Input source-built browser checksum failed')
    with tempfile.TemporaryDirectory(prefix='livara-resource-package-',dir=archive.parent) as directory:
        temp=Path(directory)
        with tarfile.open(archive) as source:source.extractall(temp,filter='data')
        app=temp/'livara-browser';binary=app/'livara-browser';engine=app/'libxul.so'
        identity=json.loads((app/'livara-build.json').read_text());pin=json.loads((ROOT/'forks/browser/upstream.json').read_text())
        if identity['upstream']['commit']!=pin['commit'] or identity['binary_sha256']!=digest(binary):raise ValueError('Browser candidate identity does not match the pinned source build')
        native={path.name:digest(path) for path in (binary,engine)}
        changes=[];resource=ROOT/'forks/browser/overlay/src/livara/LivaraUI.js'
        for jar in (app/'browser/omni.ja',app/'omni.ja'):
            if jar.is_file():
                change=update_jar(jar,resource)
                if change:changes.append(change)
        if len(changes)!=1:raise ValueError('Expected exactly one source-built Livara chrome resource')
        if {path.name:digest(path) for path in (binary,engine)}!=native:raise ValueError('Native engine changed during resource packaging')
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        report={'input_archive_sha256':before,'chrome_source_commit':commit,'resources':changes,'native_hashes_unchanged':native,'scope':'Livara JS resource update of an existing full source build; native engine/executable unchanged.'}
        (app/'livara-chrome-update.json').write_text(json.dumps(report,indent=2)+'\n')
        staged=temp/archive.name
        with tarfile.open(staged,'w:xz',preset=3) as output:
            output.add(app,arcname='livara-browser')
        os.replace(staged,archive)
        checksum.write_text(digest(archive)+'  '+archive.name+'\n')
        archive.with_name('browser-resource-update.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path);args=parser.parse_args();refresh(args.archive)
if __name__=='__main__':main()
