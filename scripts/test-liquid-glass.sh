#!/usr/bin/env bash
# Run inside a disposable GNOME 46/GTK4 test container with a private D-Bus.
set -euo pipefail
if [[ ! -f /.dockerenv || ${EUID} != 0 || ${LIVARA_DISPOSABLE_GLASS_TEST:-} != 1 ]]; then
  echo 'Requires a disposable root container and LIVARA_DISPOSABLE_GLASS_TEST=1.' >&2
  exit 1
fi
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export LIVARA_GLASS_TEST_ROOT="$project"
export LIVARA_GLASS_TEST_OUTPUT=${LIVARA_GLASS_TEST_OUTPUT:-/out}
shell_profile=$(mktemp -d /tmp/livara-optics-profile.XXXXXX)
export XDG_RUNTIME_DIR="$shell_profile/runtime"
export XDG_DATA_HOME="$shell_profile/data"
export XDG_CONFIG_HOME="$shell_profile/config"
export GSETTINGS_SCHEMA_DIR="$shell_profile/schemas"
export LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1 GTK_A11Y=none
mkdir -p /run/dbus
dbus-daemon --system --fork
# With no logind, Mutter must select its built-in non-systemd login manager.
if [[ -d /run/systemd/seats ]]; then rmdir /run/systemd/seats; fi
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME/gnome-shell/extensions" "$GSETTINGS_SCHEMA_DIR" "$LIVARA_GLASS_TEST_OUTPUT"
chmod 700 "$XDG_RUNTIME_DIR"
# The private bus was started by the entrypoint before these paths existed.
# Its activated dconf service must use the same profile/runtime as Shell;
# otherwise optimistic settings writes revert when its shared cache disagrees.
dbus-update-activation-environment XDG_RUNTIME_DIR XDG_CONFIG_HOME XDG_DATA_HOME GSETTINGS_SCHEMA_DIR
rm -f "$LIVARA_GLASS_TEST_OUTPUT/production.json" "$LIVARA_GLASS_TEST_OUTPUT/verified.json"
cp "$project/share/livara/org.livara.desktop.gschema.xml" "$GSETTINGS_SCHEMA_DIR/"
glib-compile-schemas "$GSETTINGS_SCHEMA_DIR"
cp -a "$project/share/gnome-shell/extensions/livara-glass@livara.local" "$XDG_DATA_HOME/gnome-shell/extensions/"
probe="$XDG_DATA_HOME/gnome-shell/extensions/livara-material-probe@livara.local"
mkdir "$probe"
case ${LIVARA_COMPOSITOR_PROBE:-glass} in
  glass) cp "$project/scripts/liquid-glass-smoke.js" "$probe/extension.js" ;;
  browser) cp "$project/scripts/browser-wayland-smoke.js" "$probe/extension.js" ;;
  *) echo 'Unknown compositor probe.' >&2; exit 1 ;;
esac
cat > "$probe/metadata.json" <<'META'
{"uuid":"livara-material-probe@livara.local","name":"Livara optical test","description":"Disposable renderer probe","shell-version":["46"],"version":1}
META
gsettings set org.gnome.shell enabled-extensions "['livara-glass@livara.local', 'livara-material-probe@livara.local']"
gsettings set org.gnome.shell disable-user-extensions false
compositor_size=${LIVARA_COMPOSITOR_SIZE:-1280x900}
[[ $compositor_size =~ ^[0-9]{3,4}x[0-9]{3,4}$ ]] || { echo 'Invalid virtual monitor size.' >&2; exit 1; }
timeout --kill-after=5s 60s gnome-shell --headless --wayland --no-x11 --virtual-monitor "$compositor_size" --sm-disable \
  2>&1 | tee "$LIVARA_GLASS_TEST_OUTPUT/compositor.log"
if [[ ${LIVARA_COMPOSITOR_PROBE:-glass} == browser ]]; then
  python3 - "$LIVARA_GLASS_TEST_OUTPUT" <<'PY'
import json,re,sys
from pathlib import Path
output=Path(sys.argv[1])
report=json.loads((output/'browser.json').read_text())
assert report['status']=='passed',report
assert not re.search(r'(?:Gjs|Clutter|GLib-GObject)-CRITICAL|JS ERROR',(output/'compositor.log').read_text())
print(json.dumps(report,indent=2))
PY
else
  python3 "$project/scripts/check-liquid-glass-pixels.py" "$LIVARA_GLASS_TEST_OUTPUT"
fi
