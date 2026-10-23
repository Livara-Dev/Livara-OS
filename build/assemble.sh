#!/usr/bin/env bash
set -euo pipefail
rootfs=/build/rootfs
iso_dir=/build/iso
output=/output/livara-os-0.1.0-amd64.iso
test -d "$rootfs/usr"
rm -f "$rootfs/.dockerenv" "$rootfs/etc/resolv.conf"
ln -s ../run/systemd/resolve/stub-resolv.conf "$rootfs/etc/resolv.conf"
install -d -m 1777 "$rootfs/tmp"
install -d "$rootfs/dev" "$rootfs/proc" "$rootfs/sys" "$rootfs/run"
printf 'livara\n' > "$rootfs/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 livara\n::1 localhost ip6-localhost ip6-loopback\n' > "$rootfs/etc/hosts"
mkdir -p "$iso_dir/casper" "$iso_dir/boot/grub" "$iso_dir/.disk" /output
kernel="$(find "$rootfs/boot" -maxdepth 1 -type f -name 'vmlinuz-[0-9]*' -printf '%f\n' | sort -V | tail -1)"
test -n "$kernel"
cp "$rootfs/boot/$kernel" "$iso_dir/casper/vmlinuz"
cp "$rootfs/boot/initrd.img-${kernel#vmlinuz-}" "$iso_dir/casper/initrd"
chmod 0644 "$iso_dir/casper/vmlinuz" "$iso_dir/casper/initrd"
mksquashfs "$rootfs" "$iso_dir/casper/filesystem.squashfs" -noappend -comp zstd -Xcompression-level 9 -b 1M -processors "${LIVARA_BUILD_JOBS:-2}" -no-progress
chroot "$rootfs" dpkg-query -W --showformat='${Package} ${Version}\n' > "$iso_dir/casper/filesystem.manifest"
cp "$iso_dir/casper/filesystem.manifest" /output/livara-os-0.1.0-packages.txt
du -sx --block-size=1 "$rootfs" | cut -f1 > "$iso_dir/casper/filesystem.size"
printf 'Livara OS 0.1.0 Verdant Preview amd64\n' > "$iso_dir/.disk/info"
printf 'full_cd/single\n' > "$iso_dir/.disk/cd_type"
touch "$iso_dir/.disk/base_installable"
grub_config=/usr/local/share/livara-build/grub.cfg
[[ ! -f /project/build/grub.cfg ]] || grub_config=/project/build/grub.cfg
install -m 0644 "$grub_config" "$iso_dir/boot/grub/grub.cfg"
(cd "$iso_dir" && find . -type f ! -name md5sum.txt -print0 | sort -z | xargs -0 md5sum > md5sum.txt)
grub-mkrescue -o "$output" -volid LIVARA_OS -iso-level 3 "$iso_dir"
cd /output
sha256sum livara-os-0.1.0-amd64.iso > livara-os-0.1.0-amd64.iso.sha256
printf '\nCreated %s\n' "$output"

