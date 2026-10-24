#!/usr/bin/env bash
set -euo pipefail
[[ -f /.dockerenv && ${LIVARA_DISPOSABLE_PACKAGE_TEST:-} == 1 ]] || {
  echo 'Run only in a disposable Docker container with LIVARA_DISPOSABLE_PACKAGE_TEST=1.' >&2
  exit 2
}
old=${1:?Provide the previous real DEB}
new=${2:?Provide the new real DEB}
test "$(dpkg-deb -f "$old" Package)" = livara-desktop
test "$(dpkg-deb -f "$new" Package)" = livara-desktop
dpkg --compare-versions "$(dpkg-deb -f "$new" Version)" gt "$(dpkg-deb -f "$old" Version)"
dpkg --unpack "$old"
mkdir -p /home/livara/.config/livara /home/livara/Documents
printf 'personal look stays\n' > /home/livara/.config/livara/preferences.json
printf 'personal document stays\n' > /home/livara/Documents/evidence.txt
sha256sum /home/livara/.config/livara/preferences.json /home/livara/Documents/evidence.txt > /tmp/user-files.sha256
conffile=/etc/apt/apt.conf.d/52livara-security-updates
printf '\n// administrator customization stays\n' >> "$conffile"
sha256sum "$conffile" > /tmp/conffile.sha256
dpkg --force-confold --unpack "$new"
test "$(dpkg-query -W -f='${Version}' livara-desktop)" = "$(dpkg-deb -f "$new" Version)"
sha256sum --check /tmp/user-files.sha256 /tmp/conffile.sha256
test -f /usr/lib/python3/dist-packages/livara/app_updates.py
test -x /usr/bin/livara-session-refresh
# New conffiles remain .dpkg-new until dependency configuration completes.
test -f /etc/xdg/autostart/org.livara.SessionRefresh.desktop || test -f /etc/xdg/autostart/org.livara.SessionRefresh.desktop.dpkg-new
test -f /usr/share/livara/app-resources/browser/livara-glass.css
test -f /usr/share/icons/hicolor/scalable/apps/org.livara.Settings.svg
printf 'PASS: real previous-to-new DEB unpack upgrade, user data and administrator file preservation during unpack, new session and application resource payloads.\n'
printf 'Scope: package unpack/upgrade; APT dependency and conffile configuration remain separate installed-desktop checks.\n'
