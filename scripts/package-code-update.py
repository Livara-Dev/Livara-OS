#!/usr/bin/env python3
"""Package the tested source-built Code application as a separate OS update.

This package owns only /opt/livara-code. Desktop launchers and personal profiles
remain owned by livara-desktop and the user respectively.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from livara import __version__


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(archive, output, *, check_only=False):
    archive, output = archive.resolve(), output.resolve()
    expected = Path(str(archive) + '.sha256').read_text().split()
    if expected != [sha256(archive), archive.name]:
        raise ValueError('Source-built Code archive checksum mismatch')
    output.mkdir(parents=True, exist_ok=True)
    pin = json.loads((ROOT / 'forks/code/upstream.json').read_text())
    with tempfile.TemporaryDirectory(prefix='livara-code-deb-') as temporary:
        staging = Path(temporary)
        staging.chmod(0o755)
        opt = staging / 'opt'
        opt.mkdir()
        with tarfile.open(archive) as source:
            if any(not member.name.startswith('livara-code/') and member.name != 'livara-code' for member in source):
                raise ValueError('Code archive contains an unexpected root')
            source.extractall(opt, filter='data')
        app = opt / 'livara-code'
        manifest_path = app / 'resources/app/livara-build.json'
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get('upstream', {}).get('commit') != pin['commit'] or
                manifest.get('built') is not True or manifest.get('distribution') != 'Livara Code' or
                manifest.get('build_target') != 'vscode-linux-x64-min'):
            raise ValueError('Expected the matching fully compiled Livara Code source build')
        for name in ('overlay/core/windowControls.ts', 'overlay/core/livara.css', 'overlay/core/livara.contribution.ts'):
            if manifest.get('recipes', {}).get(name) != sha256(ROOT / 'forks/code' / name):
                raise ValueError('Compiled Code does not contain the current source fix: ' + name)
        binary = app / 'livara-code'
        if binary.read_bytes()[:4] != b'\x7fELF' or not os.access(binary, os.X_OK):
            raise ValueError('Missing native source-built Code executable')
        for relative in ('bin/livara-code', 'resources/app/out/vs/workbench/workbench.desktop.main.js',
                         'resources/app/out/vs/workbench/workbench.desktop.main.css', 'resources/app/product.json'):
            if not (app / relative).is_file():
                raise ValueError('Incomplete Code distribution: ' + relative)
        if check_only:
            print('Verified matching compiled Code source manifest, recipe hashes, archive checksum and executable; runtime not yet tested.')
            return None
        manifest['desktop_package_version'] = __version__
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        # App files are public, but do not introduce a setuid sandbox helper.
        # Livara's existing AppArmor user-namespace allowance enables Chromium's
        # normal sandbox, as exercised by code-runtime-smoke.py.
        for path in (opt, *opt.rglob('*')):
            if not path.is_symlink():
                mode = path.stat().st_mode
                path.chmod(0o755 if path.is_dir() or mode & 0o111 else 0o644)
        control = staging / 'DEBIAN'
        control.mkdir()
        control.chmod(0o755)
        (control / 'control').write_text(f'''Package: livara-code
Version: {__version__}
Architecture: amd64
Section: editors
Priority: optional
Maintainer: Livara OS contributors <livara@localhost>
Pre-Depends: python3 (>= 3.11)
Depends: livara-desktop (>= {__version__}), ca-certificates, libasound2t64, libatk-bridge2.0-0t64, libatk1.0-0t64, libatspi2.0-0t64, libc6 (>= 2.31), libcairo2, libcups2t64, libdbus-1-3, libdrm2, libexpat1, libgbm1, libglib2.0-0t64, libgtk-3-0t64, libnspr4, libnss3, libpango-1.0-0, libx11-6, libxcb1, libxcomposite1, libxdamage1, libxext6, libxfixes3, libxkbcommon0, libxrandr2, libxss1, libxtst6, xdg-utils
Description: Source-built Livara Code application update
 Ships the compiled Livara workbench and window-control fixes without an ISO.
 Personal profiles and extensions remain outside the application directory.
''')
        (control / 'control').chmod(0o644)
        preinst = f'''#!/usr/bin/python3
import json, pathlib, sys
path = pathlib.Path('/opt/livara-code')
if path.exists():
    try:
        data = json.loads((path / 'resources/app/livara-build.json').read_text())
        manifest = path / 'resources/app/livara-build.json'
        if any(part.is_symlink() for part in (manifest, *manifest.parents)) or data.get('distribution') != 'Livara Code' or data.get('upstream', {{}}).get('commit') != {pin['commit']!r}:
            raise ValueError('Existing Code installation is a different/custom build')
    except (OSError, ValueError) as error:
        print(str(error) + '; preserved. Install the matching official source-built Code update.', file=sys.stderr)
        sys.exit(1)
'''
        (control / 'preinst').write_text(preinst)
        (control / 'preinst').chmod(0o755)
        package = output / f'livara-code_{__version__}_amd64.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(staging), str(package)], check=True)
        print(f'Code-only application update: {package} ({package.stat().st_size:,} bytes)')
        return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist/update-code')
    parser.add_argument('--check-only', action='store_true', help='Validate identity before executing a reused candidate')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', __version__):
        parser.error('Invalid desktop update version')
    build(args.archive, args.output_dir, check_only=args.check_only)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
