#!/usr/bin/env bash
# Validate the actual DEB against the repository's source-compiled browser.
set -euo pipefail
if [[ ! -f /.dockerenv || ${EUID} != 0 || ${LIVARA_DISPOSABLE_GLASS_TEST:-} != 1 ]]; then
  echo 'Requires a disposable root container and LIVARA_DISPOSABLE_GLASS_TEST=1.' >&2; exit 1
fi
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
archive=${1:?Pass the verified compiled browser archive}
package=${2:?Pass the new desktop DEB}
output=${LIVARA_GLASS_TEST_OUTPUT:-/out}
mkdir -p "$output" /opt
# Unpack without configuring the full OS dependencies in this runtime image.
dpkg-deb -x "$package" /
python3 - "$archive" <<'PY'
from pathlib import Path
import hashlib,json,sys,tarfile
archive=Path(sys.argv[1])
expected=Path(str(archive)+'.sha256').read_text().split()
assert expected==[hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),archive.name]
with tarfile.open(archive) as source:source.extractall('/opt',filter='data')
PY
glib-compile-schemas /usr/share/glib-2.0/schemas
# Use the updater shipped in the DEB, not a different test-only patch routine.
env -u PYTHONPATH python3 - "$output" <<'PY'
from pathlib import Path
import hashlib,json,sys
from livara.app_updates import refresh
app=Path('/opt/livara-browser')
def native():return {name:hashlib.file_digest((app/name).open('rb'),'sha256').hexdigest() for name in ('livara-browser','libxul.so')}
before=native()
result=refresh()
assert before==native(),'Native engine/executable changed'
again=refresh()
assert again[0]['status']=='current','Update is not repeatable'
Path(sys.argv[1],'package-resource-update.json').write_text(json.dumps({'result':result,'native_unchanged':before},indent=2)+'\n')
PY
grub-script-check "$project/build/grub.cfg"
bash -n /etc/default/grub.d/90-livara-auto-boot.cfg
python3 "$project/scripts/browser-reliability-smoke.py" /opt/livara-browser "$output/reliability"
export LIVARA_COMPOSITOR_PROBE=browser
export LIVARA_COMPOSITOR_SIZE=1280x720
dbus-run-session -- bash "$project/scripts/test-liquid-glass.sh"
