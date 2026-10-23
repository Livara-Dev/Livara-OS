#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
docker_cmd=("$project_dir/scripts/docker-local.sh")
"${docker_cmd[@]}" info >/dev/null
test "$(uname -m)" = x86_64 || { echo 'This image build requires an x86_64 Linux Docker host.' >&2; exit 1; }
python3 forks/browser/prepare-toolchains.py --check
python3 scripts/build-fonts.py
bash scripts/build-code.sh
bash scripts/build-browser.sh
python3 scripts/prepare-tor-browser.py dist/forks
bash packaging/build-deb.sh
mkdir -p dist .build/rootfs
build_args=(--build-arg "LIVARA_APT_REFRESH=$(date -u +%Y-%m-%d)")
# Standard public trust bundle, passed transiently rather than baked into the OS.
if [[ -n "${CODEX_PROXY_CERT:-}" && -f "${CODEX_PROXY_CERT}" ]]; then
  build_args+=(--secret "id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt")
elif [[ -n "${LIVARA_BUILD_CA:-}" ]]; then
  build_args+=(--secret "id=proxy_ca,src=$LIVARA_BUILD_CA")
fi
"${docker_cmd[@]}" build "${build_args[@]}" --target rootfs -t livara-rootfs:0.1.0 -f build/Dockerfile .
"${docker_cmd[@]}" build "${build_args[@]}" --target assembler -t livara-assembler:0.1.0 -f build/Dockerfile .
container_id="$("${docker_cmd[@]}" create livara-rootfs:0.1.0)"
cleanup() { "${docker_cmd[@]}" rm -f "$container_id" >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${docker_cmd[@]}" run --rm --entrypoint sh \
  --mount "type=bind,src=$project_dir/.build/rootfs,dst=/rootfs" \
  livara-assembler:0.1.0 -c 'find /rootfs -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
# Extract as root in a tool container to preserve ownership, permissions, and device nodes.
"${docker_cmd[@]}" export "$container_id" | \
  "${docker_cmd[@]}" run --rm -i --entrypoint tar \
    --mount "type=bind,src=$project_dir/.build/rootfs,dst=/rootfs" \
    livara-assembler:0.1.0 -xpf - -C /rootfs
if [[ -f dist/kali-core.tar.gz ]]; then
  "${docker_cmd[@]}" run --rm --entrypoint sh \
    --mount "type=bind,src=$project_dir/.build/rootfs,dst=/rootfs" \
    --mount "type=bind,src=$project_dir/dist,dst=/output" \
    livara-assembler:0.1.0 -c 'install -m 0644 /output/kali-core.tar.gz /rootfs/usr/share/livara/toolbox/'
fi
"${docker_cmd[@]}" run --rm \
  --mount "type=bind,src=$project_dir/.build,dst=/build" \
  --mount "type=bind,src=$project_dir/dist,dst=/output" \
  -e "LIVARA_BUILD_JOBS=${LIVARA_BUILD_JOBS:-2}" \
  livara-assembler:0.1.0
echo 'ISO ready in dist/. Test in a VM before using physical media.'

