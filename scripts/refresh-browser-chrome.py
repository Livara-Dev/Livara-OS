#!/usr/bin/env python3
"""Update maintained UI and Fluent resources in a source-compiled browser package.

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
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from livara.app_updates import browser_source_plan, atomic_write


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()



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
        changes=[]
        for jar, previous, fresh in browser_source_plan(app, ROOT):
            import io
            with zipfile.ZipFile(io.BytesIO(previous)) as archive_before, zipfile.ZipFile(io.BytesIO(fresh)) as archive_after:
                for name in archive_after.namelist():
                    old = archive_before.read(name) if name in archive_before.namelist() else None
                    new = archive_after.read(name)
                    if old != new:
                        changes.append({'path':name, 'before_sha256':hashlib.sha256(old).hexdigest() if old is not None else None,
                                        'after_sha256':hashlib.sha256(new).hexdigest(),'changed':True})
            atomic_write(jar, fresh)
        if {path.name:digest(path) for path in (binary,engine)}!=native:raise ValueError('Native engine changed during resource packaging')
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        report={'input_archive_sha256':before,'chrome_source_commit':commit,'resources':changes,'native_hashes_unchanged':native,'scope':'Maintained Livara chrome and restored pinned Zen localization resources; native engine/executable unchanged.'}
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
