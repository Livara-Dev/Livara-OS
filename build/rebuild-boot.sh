#!/usr/bin/env bash
# Repack only boot settings; keep the already validated root filesystem intact.
set -euo pipefail
iso_dir=/build/iso
test -f "$iso_dir/casper/filesystem.squashfs"
install -m 0644 /project/build/grub.cfg "$iso_dir/boot/grub/grub.cfg"
grub-script-check "$iso_dir/boot/grub/grub.cfg"
(cd "$iso_dir" && find . -type f ! -name md5sum.txt -print0 | sort -z | xargs -0 md5sum > md5sum.txt)
grub-mkrescue -o /output/livara-os-0.1.0-amd64.iso.new -volid LIVARA_OS "$iso_dir"
mv -f /output/livara-os-0.1.0-amd64.iso.new /output/livara-os-0.1.0-amd64.iso
cd /output
sha256sum livara-os-0.1.0-amd64.iso > livara-os-0.1.0-amd64.iso.sha256

