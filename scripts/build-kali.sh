#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p dist
docker_cmd=("$project_dir/scripts/docker-local.sh")
"${docker_cmd[@]}" build --pull -t localhost/livara-kali:0.1.0-core -f share/livara/toolbox/Containerfile share/livara/toolbox
"${docker_cmd[@]}" save localhost/livara-kali:0.1.0-core | gzip -1 > dist/kali-core.tar.gz
sha256sum dist/kali-core.tar.gz

