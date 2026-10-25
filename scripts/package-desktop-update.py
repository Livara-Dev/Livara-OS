#!/usr/bin/env python3
"""Build a small, versioned desktop update for existing Livara installations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from livara import __version__


def installer_script(package, code_package):
    return f'''#!/usr/bin/env bash
set -Eeuo pipefail
trap 'status=$?; printf "Update stopped at line %s (exit %s). Read the error above, then retry.\\n" "$LINENO" "$status" >&2' ERR
printf 'Livara desktop update {__version__} — checking downloaded files…\\n'
cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")"
for required in {package!r} SHA256SUMS; do
  if [[ ! -f "$required" || ! -r "$required" ]]; then
    printf 'Missing or unreadable file: %s\\n' "$required" >&2
    printf 'Download the DEB files and SHA256SUMS from the same release into this folder:\\n%s\\n' 'https://github.com/Livara-Dev/Livara-OS/releases/tag/desktop-v{__version__}' >&2
    exit 1
  fi
done
for program in dpkg dpkg-query dpkg-deb apt-get awk sha256sum; do
  if ! command -v "$program" >/dev/null 2>&1; then
    printf 'Required program is missing: %s. Run this installer inside Livara OS.\\n' "$program" >&2
    exit 1
  fi
done
verify_package() {{
  local filename=$1
  local -a entries
  mapfile -t entries < <(awk -v name="$filename" '$2 == name {{print}}' SHA256SUMS)
  if ((${{#entries[@]}} != 1)); then
    echo "Expected exactly one release checksum for $filename; refusing installation." >&2; exit 1
  fi
  printf '%s\\n' "${{entries[0]}}" | sha256sum --check --strict -
}}
verify_package {package!r}
sha256sum --check --ignore-missing SHA256SUMS
if [[ $(dpkg --print-architecture) != amd64 ]]; then
  echo 'This update targets the supported Livara OS amd64 installation.' >&2; exit 1
fi
if ! dpkg-query -W -f='${{Status}}' livara-desktop 2>/dev/null | grep -qx 'install ok installed'; then
  echo 'Install this update on an existing Livara desktop, not a generic Linux host.' >&2; exit 1
fi
installed=$(dpkg-query -W -f='${{Version}}' livara-desktop)
if dpkg --compare-versions "$installed" gt {__version__!r}; then
  echo 'A newer Livara desktop is already installed; refusing to downgrade it.' >&2; exit 1
fi
packages=(./{package})
if [[ -d /opt/livara-code && ! -f {code_package!r} ]]; then
  echo 'Download {code_package} from the same release beside this installer to update the installed Code app.' >&2
  exit 1
fi
if [[ -f {code_package!r} ]]; then
  verify_package {code_package!r}
  if [[ $(dpkg-deb -f {code_package!r} Package) != livara-code || $(dpkg-deb -f {code_package!r} Version) != {__version__!r} ]]; then
    echo 'The Code update does not match this desktop release.' >&2; exit 1
  fi
  installed_code=$(dpkg-query -W -f='${{Version}}' livara-code 2>/dev/null || true)
  if [[ -n "$installed_code" ]] && dpkg --compare-versions "$installed_code" gt {__version__!r}; then
    echo 'A newer Livara Code is already installed; refusing to downgrade it.' >&2; exit 1
  fi
  packages+=(./{code_package})
fi
echo 'Files verified. Installing the update; APT may request your administrator password or confirmation.'
if ((EUID == 0)); then
  apt-get install -- "${{packages[@]}}"
else
  sudo apt-get install -- "${{packages[@]}}"
  if command -v livara-session-refresh >/dev/null 2>&1; then
    livara-session-refresh || echo 'Log out and back in to refresh desktop styling.' >&2
  fi
fi
echo 'Update installed. Close and reopen Livara apps, then log out and back in for GNOME Shell changes.'
echo 'Live ISO sessions are ephemeral: keep the update files on persistent storage for later sessions.'
'''


def bundle_update(output, names):
    """Keep all required files together in one versioned download folder."""
    destination = output / f'Livara-Halo-{__version__}-Update.zip'
    temporary = destination.with_suffix('.zip.part')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name in (*names, 'SHA256SUMS'):
                archive.write(output / name, f'Livara-Halo-{__version__}-Update/{name}')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Update ZIP failed its CRC integrity check')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist/update')
    parser.add_argument('--code-package', type=Path, help='Include the separately compiled and runtime-tested Code DEB')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', __version__):
        parser.error('Expected a stable three-part desktop package version')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(['bash', str(ROOT / 'packaging/build-deb.sh'), str(output)], check=True)
    package = f'livara-desktop_{__version__}_all.deb'
    code_package = f'livara-code_{__version__}_amd64.deb'
    if args.code_package:
        for field, expected in (('Package', 'livara-code'), ('Version', __version__), ('Architecture', 'amd64')):
            actual = subprocess.check_output(['dpkg-deb', '-f', str(args.code_package), field], text=True).strip()
            if actual != expected:
                raise ValueError(f'Unexpected Code package {field}: {actual}')
        if args.code_package.resolve() != output / code_package:
            shutil.copy2(args.code_package, output / code_package)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    manifest = {'package': package, 'version': __version__, 'source_commit': revision, 'source_dirty': dirty,
                'scope': 'Desktop applications, icons, GNOME Shell material, matching Browser resources and separately source-compiled Code update. No Browser engine, kernel, boot image or ISO replacement.',
                'sha256': hashlib.sha256((output / package).read_bytes()).hexdigest()}
    if args.code_package:
        manifest['code_package'] = code_package
        manifest['code_sha256'] = hashlib.sha256((output / code_package).read_bytes()).hexdigest()
    (output / 'update-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    installer = installer_script(package, code_package)
    (output / 'Install-Livara-Update.sh').write_text(installer)
    (output / 'Install-Livara-Update.sh').chmod(0o755)
    (output / 'README.txt').write_text(f'''Livara desktop {__version__} — update an existing installation without an ISO

Download the desktop DEB, SHA256SUMS, update-manifest.json and Install-Livara-Update.sh
from this repository's official HTTPS GitHub release into the same folder.
If Livara Code is installed, also download {code_package} into that folder.
Read docs/updates.md in the source for the scope and recovery details.
Run: bash Install-Livara-Update.sh

Check the release origin before running its installer. SHA256SUMS detects
corruption; it is not a detached signature and does not establish who published
the files. Hosted releases may also carry GitHub artifact provenance.

The package upgrades only Livara's desktop layer and first-party UI resources.
It preserves home directories, personal settings, files and application profiles.
Kernel/driver/security packages continue through Ubuntu's signed APT sources.
Matching source-built Browser/Code resources are refreshed with original-file
backups in /var/lib/livara/app-resource-backups. Restart those apps afterward.
A mismatched/custom app build is left untouched and reported during installation;
inspect the warning and run sudo livara-refresh-app-resources when appropriate.
The separate Code DEB ships the tested source-compiled application, including
window-control behavior fixes. It replaces only /opt/livara-code and preserves
personal profiles/extensions. No Browser engine or full OS/ISO rebuild is used.

Log out and in for GNOME Shell styling; no reboot or ISO download is required.
An installed system retains the update. A nonpersistent live USB does not retain
any package changes across reboot; retain this small package on another drive.

Source commit: {revision}
Source contains uncommitted changes: {dirty}
''')
    names = [package, 'update-manifest.json', 'Install-Livara-Update.sh', 'README.txt']
    if args.code_package:
        names.append(code_package)
    (output / 'SHA256SUMS').write_text(''.join(hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names))
    if args.code_package:
        print('Complete update ZIP:', bundle_update(output, names))
    print(f'Desktop update created: {output / package} ({(output / package).stat().st_size:,} bytes)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
