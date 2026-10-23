#!/usr/bin/env bash
# Runs only when the live image is booted with livara.selftest on its kernel line.
set -euo pipefail
trap 'echo LIVARA_SELFTEST_FAIL line=$LINENO; journalctl -b _COMM=gnome-shell --no-pager -n 60; journalctl -b -p warning --no-pager -n 40; echo LIVARA_SELFTEST_LOG_END; exit 1' ERR
echo LIVARA_SELFTEST_START
test -f /cdrom/casper/filesystem.squashfs
test "$(. /etc/os-release; printf '%s' "$ID")" = livara
getent passwd livara
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 livara
live_uid="$(id -u livara)"
user_cmd=(runuser -u livara -- env "XDG_RUNTIME_DIR=/run/user/$live_uid" "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$live_uid/bus")
"${user_cmd[@]}" livara status --json
"${user_cmd[@]}" livara shield --json
"${user_cmd[@]}" nmap --version
test_dir="$(mktemp -d /tmp/livara-selftest.XXXXXX)"
chown livara:livara "$test_dir"
"${user_cmd[@]}" livara case new boot-check --directory "$test_dir"
"${user_cmd[@]}" livara case seal "$test_dir/boot-check"
"${user_cmd[@]}" livara case verify "$test_dir/boot-check"
rm -rf -- "$test_dir"
for attempt in $(seq 1 90); do
  if pgrep -u "$live_uid" -x gnome-shell >/dev/null; then break; fi
  sleep 2
done
pgrep -u "$live_uid" -x gnome-shell
echo LIVARA_DESKTOP_OK
for attempt in $(seq 1 90); do
  if pgrep -u "$live_uid" -f '/usr/bin/livara-center' >/dev/null; then break; fi
  sleep 1
done
pgrep -u "$live_uid" -f '/usr/bin/livara-center'
echo LIVARA_CENTER_OK
for attempt in $(seq 1 30); do
  extension_info="$("${user_cmd[@]}" timeout 5 gnome-extensions info livara-glass@livara.local 2>&1 || true)"
  if grep -Eq 'State: (ENABLED|ACTIVE)' <<< "$extension_info"; then break; fi
  printf 'Waiting for glass extension: attempt %s\n' "$attempt"
  sleep 3
done
printf '%s\n' "$extension_info"
grep -Eq 'State: (ENABLED|ACTIVE)' <<< "$extension_info"
"${user_cmd[@]}" gsettings get org.livara.desktop accent
"${user_cmd[@]}" clamscan --version
"${user_cmd[@]}" yara --version
"${user_cmd[@]}" hashdeep -V
echo LIVARA_GLASS_AND_EXTRA_TOOLS_OK
test -f /home/livara/.config/livara/live-initialized
"${user_cmd[@]}" gsettings get org.gnome.shell.extensions.dash-to-dock dock-position | grep BOTTOM
"${user_cmd[@]}" gsettings get org.gnome.desktop.background picture-uri | grep '/livara/livara-glass.png'
echo LIVARA_DEFAULTS_OK
if [[ -f /usr/share/livara/toolbox/kali-core.tar.gz ]]; then
  "${user_cmd[@]}" livara toolbox setup
  "${user_cmd[@]}" livara toolbox run -- cat /etc/os-release
  "${user_cmd[@]}" livara toolbox run -- nmap --version
  echo LIVARA_KALI_OK
fi
pgrep -u "$live_uid" -x gnome-shell
pgrep -u "$live_uid" -f '/usr/bin/livara-center'
if pgrep -u "$live_uid" -f 'gnome-session-failed' >/dev/null; then
  echo LIVARA_SELFTEST_FAIL graphical-session
  exit 1
fi
echo LIVARA_SELFTEST_PASS

