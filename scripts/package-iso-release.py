#!/usr/bin/env python3
"""Prepare a built ISO for GitHub Releases, preserving its exact bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

LIMIT=1_900_000_000


def sha256(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def package(iso, output, limit=LIMIT):
    if not iso.is_file() or iso.is_symlink() or iso.suffix!='.iso' or not re.fullmatch(r'[A-Za-z0-9_.-]+',iso.name):raise ValueError('Use a real ISO with a portable filename')
    if not 1<=limit<=LIMIT:raise ValueError('Invalid release part size')
    if output.exists() and any(output.iterdir()):raise ValueError('Release directory must be empty')
    output.mkdir(parents=True,exist_ok=True)
    size=iso.stat().st_size
    if size==0:raise ValueError('The ISO is empty')
    full_digest=hashlib.sha256();parts=[]
    with iso.open('rb') as source:
        number=1;written=0
        while written<size:
            filename=iso.name if size<=limit else f'{iso.name}.{number:03d}'
            path=output/filename;digest=hashlib.sha256();count=0
            with path.open('wb') as target:
                while count<limit:
                    block=source.read(min(8*1024*1024,limit-count))
                    if not block:break
                    target.write(block);digest.update(block);full_digest.update(block);count+=len(block)
            parts.append({'name':filename,'bytes':count,'sha256':digest.hexdigest()});written+=count;number+=1
    digest=full_digest.hexdigest()
    if iso.stat().st_size!=size:raise ValueError('ISO changed while packaging')
    if sha256(iso)!=digest:raise ValueError('ISO content changed while packaging')
    checks=''.join(p['sha256']+'  '+p['name']+'\n' for p in parts)
    (output/'SHA256SUMS').write_text(checks)
    (output/(iso.name+'.sha256')).write_text(digest+'  '+iso.name+'\n')
    if len(parts)>1:
        names=[p['name'] for p in parts]
        lines=['@echo off','setlocal','cd /d "%~dp0"']
        lines += ['if not exist "'+name+'" goto missing' for name in names]
        lines += ['copy /b /y '+'+'.join('"'+name+'"' for name in names)+' "'+iso.name+'.partial" >nul','if errorlevel 1 goto failed',f'powershell.exe -NoProfile -Command "if ((Get-FileHash -LiteralPath \'{iso.name}.partial\' -Algorithm SHA256).Hash -ne \'{digest}\') {{ exit 1 }}"','if errorlevel 1 goto failed','move /y "'+iso.name+'.partial" "'+iso.name+'" >nul','if errorlevel 1 goto failed','echo ISO reconstructed and SHA-256 verified.','pause','exit /b 0',':missing','echo Download every numbered ISO part into this folder first.','pause','exit /b 1',':failed','echo Joining or checksum verification failed. Do not flash an unverified ISO.','pause','exit /b 1']
        (output/'Join-Livara-ISO.bat').write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
        script='#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nsha256sum --check SHA256SUMS\ncat -- '+' '.join('"'+name+'"' for name in names)+' > "'+iso.name+'.partial"\nprintf \'%s  %s\\n\' "'+digest+'" "'+iso.name+'.partial" | sha256sum --check -\nmv -- "'+iso.name+'.partial" "'+iso.name+'"\n'
        (output/'Join-Livara-ISO.sh').write_text(script);(output/'Join-Livara-ISO.sh').chmod(0o755)
    manifest={'iso':iso.name,'bytes':size,'sha256':digest,'parts':parts,'bit_identical_after_join':True}
    (output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    instructions=f'''Livara OS x86-64 experimental preview

ISO: {iso.name}
Bytes: {size}
SHA-256: {digest}

This release is produced from the repository's compiled application artifacts
and signed distribution packages. Its publication job requires the real ISO
to pass BIOS and UEFI QEMU boot/self-tests. Build logs, provenance and boot
proof are retained with the publishing Actions run.

'''
    if len(parts)>1:instructions+='GitHub limits individual release files to 2 GB. Download ALL numbered ISO\nparts and Join-Livara-ISO.bat into ONE folder, then run the BAT to reconstruct\nand verify the complete .iso. On Linux, download SHA256SUMS and run the .sh\njoiner. The numbered parts are pieces of the same ISO, not separate images.\n\n'
    else:instructions+='Download the ISO and its .sha256 file. Verify it before flashing a USB.\n\n'
    instructions+='This is an experimental preview. QEMU boot tests do not qualify physical\nRTX/Core Ultra hardware, Secure Boot, encrypted disk installation or recovery.\nBack up your data and test in a virtual machine before using physical media.\n'
    (output/'README.txt').write_text(instructions)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('iso',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();print(json.dumps(package(args.iso,args.output),indent=2))
if __name__=='__main__':main()
