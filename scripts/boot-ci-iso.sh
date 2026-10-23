#!/usr/bin/env bash
# Boot an existing ISO; retain separate BIOS and UEFI logs and original captures.
set -euo pipefail
case "${1:-}" in
  bios|uefi) firmware=$1 ;;
  *) echo 'Usage: boot-ci-iso.sh bios|uefi' >&2; exit 2 ;;
esac
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(cd "$project_dir/dist" && sha256sum --check livara-os-0.1.0-amd64.iso.sha256)
"$project_dir/scripts/docker-local.sh" run --rm --entrypoint python3 \
  --mount "type=bind,src=$project_dir,dst=/project" \
  livara-assembler:0.1.0 /project/scripts/boot-smoke.py --firmware "$firmware" --timeout 1800 --capture-menus
