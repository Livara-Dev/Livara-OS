#!/usr/bin/env bash
# Validate the image's boot kernel, never the Docker host or a modules directory.
set -euo pipefail
rootfs=$(realpath -e -- "${1:-/}")
kernel_image=$(find "$rootfs/boot" -maxdepth 1 -type f -name 'vmlinuz-[0-9]*' -printf '%f\n' | sort -V | tail -n 1)
test -n "$kernel_image" || { echo 'Livara: no installed boot kernel image' >&2; exit 1; }
kernel=${kernel_image#vmlinuz-}
for required in "$rootfs/boot/$kernel_image" "$rootfs/boot/config-$kernel" \
  "$rootfs/lib/modules/$kernel/modules.builtin"; do
  test -s "$required" || { echo "Livara: missing kernel file: $required" >&2; exit 1; }
done
# NVIDIA packages can add modules after the image package's first depmod run.
depmod -b "$rootfs" -a "$kernel"
nvidia_version=$(modinfo -b "$rootfs" -k "$kernel" -F version nvidia)
nvidia_license=$(modinfo -b "$rootfs" -k "$kernel" -F license nvidia)
case "$nvidia_version" in
  580.*) ;;
  *) echo "Livara: expected NVIDIA 580 modules for $kernel; found $nvidia_version" >&2; exit 1 ;;
esac
case "$nvidia_license" in
  *MIT*GPL*|*GPL*MIT*) ;;
  *) echo "Livara: expected NVIDIA open kernel modules; license is $nvidia_license" >&2; exit 1 ;;
esac
for module in nvidia nvidia_modeset nvidia_drm nvidia_uvm nvidia_peermem; do
  filename=$(modinfo -b "$rootfs" -k "$kernel" -F filename "$module")
  vermagic=$(modinfo -b "$rootfs" -k "$kernel" -F vermagic "$module")
  test "${vermagic%% *}" = "$kernel" || {
    echo "Livara: $module does not match boot kernel $kernel: $vermagic" >&2; exit 1;
  }
  printf 'Livara kernel check: %s %s\n' "$kernel" "$filename" >&2
done
printf 'Livara kernel check: NVIDIA %s (%s) passed\n' "$nvidia_version" "$nvidia_license" >&2
printf '%s\n' "$kernel"
