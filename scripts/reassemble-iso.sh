#!/usr/bin/env bash
# Development rebuild: reuse an already exported Ubuntu filesystem after app changes.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
test -d .build/rootfs || { echo 'Run make iso to export the Ubuntu filesystem first.' >&2; exit 1; }
bash packaging/build-deb.sh
"$project_dir/scripts/docker-local.sh" run --rm --privileged --entrypoint bash \
  --mount "type=bind,src=$project_dir,dst=/project,readonly" \
  --mount "type=bind,src=$project_dir/.build,dst=/build" \
  --mount "type=bind,src=$project_dir/dist,dst=/output" \
  -e "LIVARA_BUILD_JOBS=${LIVARA_BUILD_JOBS:-2}" \
  livara-assembler:0.1.0 /project/build/refresh-rootfs.sh

