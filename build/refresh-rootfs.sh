#!/usr/bin/env bash
set -euo pipefail
rootfs=/build/rootfs
test -f "$rootfs/var/lib/dpkg/status"
dpkg-deb -x /output/livara-desktop_0.1.0_all.deb "$rootfs"
install -D -m 0755 /project/build/live-selftest.sh "$rootfs/usr/lib/livara/live-selftest"
install -m 0644 /project/build/livara-selftest.service "$rootfs/etc/systemd/system/"
install -m 0644 /project/build/configure-rootfs.sh "$rootfs/tmp/livara-configure.sh"
mount --bind /dev "$rootfs/dev"
mount -t proc proc "$rootfs/proc"
mount --rbind /sys "$rootfs/sys"
mount --make-rslave "$rootfs/sys"
cleanup() {
  umount -R "$rootfs/sys" || true
  umount "$rootfs/proc" || true
  umount "$rootfs/dev" || true
}
trap cleanup EXIT
# Bring a prior export up to date when new desktop dependencies are added.
missing_packages=()
while IFS= read -r package; do
  [[ -n "$package" && "$package" != \#* ]] || continue
  installed_state="$(chroot "$rootfs" dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)"
  [[ "$installed_state" == installed ]] || missing_packages+=("$package")
done < /project/build/packages.txt
if [[ ${#missing_packages[@]} -gt 0 ]]; then
  cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf.build"
  rm -f "$rootfs/etc/resolv.conf"
  mv "$rootfs/etc/resolv.conf.build" "$rootfs/etc/resolv.conf"
  chroot "$rootfs" apt-get update
  chroot "$rootfs" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing_packages[@]}"
  chroot "$rootfs" apt-get clean
  rm -rf "$rootfs/var/lib/apt/lists/"*
fi
# Reinstall package metadata and run the same defaults used by a fresh image build.
cp /output/livara-desktop_0.1.0_all.deb "$rootfs/tmp/livara-desktop.deb"
chroot "$rootfs" dpkg -i /tmp/livara-desktop.deb
chroot "$rootfs" bash /tmp/livara-configure.sh
rm -f "$rootfs/tmp/livara-desktop.deb" "$rootfs/tmp/livara-configure.sh"
cleanup
trap - EXIT
if [[ -f /output/kali-core.tar.gz ]]; then
  install -m 0644 /output/kali-core.tar.gz "$rootfs/usr/share/livara/toolbox/"
fi
exec bash /project/build/assemble.sh

