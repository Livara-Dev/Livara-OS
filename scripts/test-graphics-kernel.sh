#!/usr/bin/env bash
# Reproduce kernel selection using downloaded, APT-verified Ubuntu packages.
# Requires kmod and a directory containing image, main-modules and NVIDIA DEBs.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
packages=$(realpath -e -- "${1:?Supply the directory of verified kernel DEBs}")
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
rootfs=$fixture/rootfs
mkdir -p "$rootfs"
for package in "$packages"/linux-*.deb; do
  dpkg-deb -x "$package" "$rootfs"
done
# This real directory in Ubuntu's NVIDIA package triggered the original failure.
old_selection=$(find "$rootfs/lib/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -n 1)
test "$old_selection" = kernel
if modinfo -b "$rootfs" -k "$old_selection" nvidia >/dev/null 2>&1; then
  echo 'Regression fixture did not reproduce the original lookup failure' >&2; exit 1
fi
echo 'PASS: reproduced the old selection of the non-version kernel directory'
kernel=$(bash "$project_dir/build/verify-graphics-kernel.sh" "$rootfs")
test -s "$rootfs/boot/vmlinuz-$kernel"
echo "PASS: real boot image and five NVIDIA modules match $kernel"

drm=$(modinfo -b "$rootfs" -k "$kernel" -F filename nvidia_drm)
mv -- "$drm" "$fixture/nvidia-drm.ko"
if bash "$project_dir/build/verify-graphics-kernel.sh" "$rootfs" >"$fixture/output" 2>&1; then
  echo 'Missing NVIDIA DRM module was accepted' >&2; exit 1
fi
mv -- "$fixture/nvidia-drm.ko" "$drm"
echo 'PASS: missing NVIDIA DRM module is rejected'

cp -- "$rootfs/boot/vmlinuz-$kernel" "$rootfs/boot/vmlinuz-99.0.0-1-generic"
if bash "$project_dir/build/verify-graphics-kernel.sh" "$rootfs" >"$fixture/output" 2>&1; then
  echo 'A newer boot image without matching modules was accepted' >&2; exit 1
fi
rm -- "$rootfs/boot/vmlinuz-99.0.0-1-generic"
echo 'PASS: newer incomplete kernel is rejected instead of silently selecting an older one'

rm -- "$rootfs/boot/vmlinuz-$kernel"
if bash "$project_dir/build/verify-graphics-kernel.sh" "$rootfs" >"$fixture/output" 2>&1; then
  echo 'A modules tree without a boot image was accepted' >&2; exit 1
fi
echo 'PASS: modules without a boot image are rejected'
