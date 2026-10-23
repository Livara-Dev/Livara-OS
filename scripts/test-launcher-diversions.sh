#!/bin/bash
set -euo pipefail
# This test deliberately installs/removes packages; never run it on a host.
[[ -f /.dockerenv && ${LIVARA_DISPOSABLE_PACKAGE_TEST:-} == 1 ]] || {
  echo 'Run only in a disposable Docker container with LIVARA_DISPOSABLE_PACKAGE_TEST=1.' >&2
  exit 2
}
package=${1:?Provide the actual Livara DEB path}
test -f "$package"
names=(org.gnome.Epiphany org.gnome.Settings org.gnome.SystemMonitor org.gnome.Terminal)
make_vendor() {
  local version=$1
  mkdir -p /tmp/vendor/DEBIAN /tmp/vendor/usr/share/applications
  printf 'Package: livara-test-vendor\nVersion: %s\nArchitecture: all\nMaintainer: Livara test <test@localhost>\nDescription: Disposable ownership fixture\n' "$version" > /tmp/vendor/DEBIAN/control
  for name in "${names[@]}"; do printf 'vendor-version=%s\n' "$version" > "/tmp/vendor/usr/share/applications/$name.desktop"; done
  dpkg-deb --build /tmp/vendor "/tmp/vendor-$version.deb"
}
make_vendor 1
dpkg -i /tmp/vendor-1.deb
dpkg --unpack "$package"
for name in "${names[@]}"; do
  test "$(dpkg-divert --listpackage "/usr/share/applications/$name.desktop")" = livara-desktop
  grep -q 'vendor-version=1' "/usr/share/applications/$name.desktop.livara-vendor"
done
sha256sum /usr/share/applications/org.gnome.*.desktop > /tmp/aliases.sha256
dpkg --unpack "$package"
make_vendor 2
dpkg -i /tmp/vendor-2.deb
sha256sum --check /tmp/aliases.sha256
for name in "${names[@]}"; do grep -q 'vendor-version=2' "/usr/share/applications/$name.desktop.livara-vendor"; done
dpkg --remove livara-desktop
for name in "${names[@]}"; do
  grep -q 'vendor-version=2' "/usr/share/applications/$name.desktop"
  test ! -e "/usr/share/applications/$name.desktop.livara-vendor"
  test -z "$(dpkg-divert --listpackage "/usr/share/applications/$name.desktop")"
done
printf 'PASS: actual Livara DEB unpack/re-unpack, vendor upgrade preservation, removal and restoration of all four launchers.\n'
