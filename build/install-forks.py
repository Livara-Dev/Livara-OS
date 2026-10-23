#!/usr/bin/env python3
"""Install trusted locally-built x86-64 Livara application archives in an image.

This is called by the live-rootfs Dockerfile, never by a normal desktop user.
Archives must have a single expected root, safe internal links and an amd64 ELF.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile

APPS = {
    'code': ('livara-code-linux-x64.tar.xz', 'livara-code', 'livara-code'),
    'browser': ('livara-browser-linux-x64.tar.xz', 'livara-browser', 'livara-browser'),
    'tor': ('livara-tor-browser-linux-x64.tar.xz', 'tor-browser', 'Browser/firefox.real'),
}


def validate_elf(path: Path) -> None:
    with path.open('rb') as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 62:
        raise ValueError(f'{path} must be a 64-bit x86-64 Linux executable')


def validate_members(members: list[tarfile.TarInfo], expected: str) -> None:
    total = 0
    for item in members:
        path = PurePosixPath(item.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != expected:
            raise ValueError(f'Unexpected archive path: {item.name}')
        if not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
            raise ValueError(f'Special files are not application assets: {item.name}')
        total += item.size
        if total > 8 * 1024**3:
            raise ValueError('Application archive exceeds the 8 GiB unpacked budget')
        if item.issym() or item.islnk():
            target = PurePosixPath(item.linkname)
            if target.is_absolute():
                raise ValueError(f'Absolute archive link: {item.name}')
            # Hard-link names are archive-relative; symbolic links are parent-relative.
            parts = list(path.parent.parts) if item.issym() else []
            for part in target.parts:
                if part == '..':
                    if len(parts) <= 1:
                        raise ValueError(f'Archive link escapes its application: {item.name}')
                    parts.pop()
                elif part != '.':
                    parts.append(part)
            if not parts or parts[0] != expected:
                raise ValueError(f'Archive link escapes its application: {item.name}')


def install(archives: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for app, (archive_name, root, binary) in APPS.items():
        archive = archives / archive_name
        target = destination / root
        if target.exists():
            raise ValueError(f'Refusing to merge into an existing application: {target}')
        with tarfile.open(archive, 'r:xz') as source:
            members = source.getmembers()
            validate_members(members, root)
            source.extractall(destination, members=members, filter='data')
        validate_elf(target / binary)
        # Builds may inherit a private umask; the official Tor archive also uses
        # 0700/0600. Root-owned applications must be readable by desktop users.
        # Change modes only, preserving executable bits and every input byte.
        for directory, _folders, filenames in os.walk(target, followlinks=False):
            folder = Path(directory)
            folder.chmod(0o755)
            for name in filenames:
                file_path = folder / name
                if not file_path.is_symlink():
                    executable = bool(file_path.stat().st_mode & 0o111)
                    file_path.chmod(0o755 if executable else 0o644)
        if app == 'tor':
            if not (target / 'Browser/start-tor-browser').is_file():
                raise ValueError('The official Tor Browser launcher is missing')
        if app == 'code':
            cli = target / 'bin/livara-code'
            if not cli.is_file():
                raise ValueError('Livara Code command-line launcher is missing')
            cli.chmod(0o755)
            sandbox = target / 'chrome-sandbox'
            if sandbox.exists():
                if sandbox.is_symlink() or not sandbox.is_file():
                    raise ValueError('Electron sandbox helper must be a regular file')
                os.chown(sandbox, 0, 0)
                sandbox.chmod(stat.S_ISUID | 0o755)
        (target / binary).chmod(0o755)
        print(f'Installed {root}: ELF64 x86-64 confirmed')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', type=Path)
    parser.add_argument('--destination', type=Path, default=Path('/opt'))
    args = parser.parse_args()
    install(args.archives, args.destination)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
