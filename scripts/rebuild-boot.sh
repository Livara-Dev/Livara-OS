#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
"$project_dir/scripts/docker-local.sh" run --rm --entrypoint bash \
  --mount "type=bind,src=$project_dir,dst=/project,readonly" \
  --mount "type=bind,src=$project_dir/.build,dst=/build" \
  --mount "type=bind,src=$project_dir/dist,dst=/output" \
  livara-assembler:0.1.0 /project/build/rebuild-boot.sh

