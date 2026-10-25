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
export GSETTINGS_SCHEMA_DIR="$shell_profile/schemas"
export LIBGL_ALWAYS_SOFTWARE=1 NO_AT_BRIDGE=1 GTK_A11Y=none
mkdir -p /run/dbus
dbus-daemon --system --fork
# With no logind, Mutter must select its built-in non-systemd login manager.
if [[ -d /run/systemd/seats ]]; then rmdir /run/systemd/seats; fi
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_DATA_HOME/gnome-shell/extensions" "$GSETTINGS_SCHEMA_DIR" "$LIVARA_GLASS_TEST_OUTPUT"
chmod 700 "$XDG_RUNTIME_DIR"
rm -f "$LIVARA_GLASS_TEST_OUTPUT/production.json" "$LIVARA_GLASS_TEST_OUTPUT/verified.json"
cp "$project/share/livara/org.livara.desktop.gschema.xml" "$GSETTINGS_SCHEMA_DIR/"
glib-compile-schemas "$GSETTINGS_SCHEMA_DIR"
cp -a "$project/share/gnome-shell/extensions/livara-glass@livara.local" "$XDG_DATA_HOME/gnome-shell/extensions/"
probe="$XDG_DATA_HOME/gnome-shell/extensions/livara-material-probe@livara.local"
mkdir "$probe"
cp "$project/scripts/liquid-glass-smoke.js" "$probe/extension.js"
cat > "$probe/metadata.json" <<'META'
{"uuid":"livara-material-probe@livara.local","name":"Livara optical test","description":"Disposable renderer probe","shell-version":["46"],"version":1}
META
gsettings set org.gnome.shell enabled-extensions "['livara-glass@livara.local', 'livara-material-probe@livara.local']"
gsettings set org.gnome.shell disable-user-extensions false
timeout --kill-after=5s 60s gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x900 --sm-disable \
  2>&1 | tee "$LIVARA_GLASS_TEST_OUTPUT/compositor.log"
python3 "$project/scripts/check-liquid-glass-pixels.py" "$LIVARA_GLASS_TEST_OUTPUT"
