"""Refresh installed GRUB after the package's managed auto-boot defaults change."""
from pathlib import Path
import os
import shutil
import subprocess
import sys


def refresh(*, root=Path('/'), runner=subprocess.run, command=None):
    cmdline = (root / 'proc/cmdline').read_text().split()
    mounts = (root / 'proc/mounts').read_text().splitlines()
    live = 'boot=casper' in cmdline or any(
        len(fields := line.split()) > 2 and fields[1] == '/' and
        fields[2] in ('overlay', 'squashfs', 'tmpfs') for line in mounts)
    if live:
        return 'Live media boot files are read-only; auto-boot defaults apply to installed systems and future images.'
    if not (root / 'boot/grub/grub.cfg').is_file():
        return 'No installed GRUB configuration; auto-boot defaults are ready for the next GRUB configuration.'
    command = command or shutil.which('update-grub')
    if not command:
        raise ValueError('GRUB defaults were installed, but update-grub is unavailable. Run sudo update-grub after installing grub2-common.')
    runner([command], check=True, timeout=180)
    return 'Main OS auto-boot enabled. Press Esc during startup to reveal the boot menu.'


def main():
    if os.geteuid() != 0:
        print('Run sudo livara-refresh-boot to refresh installed GRUB.', file=sys.stderr)
        return 1
    try:
        print(refresh())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Livara boot configuration: {error}', file=sys.stderr)
        return 1
    return 0
