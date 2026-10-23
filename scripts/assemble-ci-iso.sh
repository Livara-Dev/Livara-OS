#!/usr/bin/env bash
# Assemble an ISO from already compiled and checksum-verified CI applications.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"
docker_cmd=("$project_dir/scripts/docker-local.sh")
mkdir -p dist .build/rootfs
for app in code browser; do
  (cd dist/forks && sha256sum --check "livara-$app-linux-x64.tar.xz.sha256")
done
python3 scripts/build-fonts.py
bash packaging/build-deb.sh
python3 scripts/prepare-tor-browser.py dist/forks
refresh_date=$(date -u +%Y-%m-%d)
"${docker_cmd[@]}" build --pull --build-arg "LIVARA_APT_REFRESH=$refresh_date" \
  -t localhost/livara-kali:0.1.0-core -f share/livara/toolbox/Containerfile share/livara/toolbox
"${docker_cmd[@]}" save localhost/livara-kali:0.1.0-core | gzip -1 > dist/kali-core.tar.gz
"${docker_cmd[@]}" build --build-arg "LIVARA_APT_REFRESH=$refresh_date" --target rootfs -t livara-rootfs:0.1.0 -f build/Dockerfile .
"${docker_cmd[@]}" build --target assembler -t livara-assembler:0.1.0 -f build/Dockerfile .
container_id=$("${docker_cmd[@]}" create livara-rootfs:0.1.0)
cleanup() { "${docker_cmd[@]}" rm -f "$container_id" >/dev/null 2>&1 || true; }
trap cleanup EXIT
# Empty destination only; never recursively remove an existing build here.
test -z "$(ls -A .build/rootfs)" || { echo 'CI rootfs destination must be empty' >&2; exit 1; }
"${docker_cmd[@]}" export "$container_id" | "${docker_cmd[@]}" run --rm -i --entrypoint tar \
  --mount "type=bind,src=$project_dir/.build/rootfs,dst=/rootfs" livara-assembler:0.1.0 -xpf - -C /rootfs
"${docker_cmd[@]}" run --rm --entrypoint sh \
  --mount "type=bind,src=$project_dir/.build/rootfs,dst=/rootfs" \
  --mount "type=bind,src=$project_dir/dist,dst=/output,readonly" livara-assembler:0.1.0 \
  -c 'install -m 0644 /output/kali-core.tar.gz /rootfs/usr/share/livara/toolbox/'
"${docker_cmd[@]}" run --rm \
  --mount "type=bind,src=$project_dir/.build,dst=/build" \
  --mount "type=bind,src=$project_dir/dist,dst=/output" \
  -e "LIVARA_BUILD_JOBS=${LIVARA_BUILD_JOBS:-2}" livara-assembler:0.1.0
(cd dist && sha256sum --check livara-os-0.1.0-amd64.iso.sha256)
for firmware in bios uefi; do
  "${docker_cmd[@]}" run --rm --entrypoint python3 \
    --mount "type=bind,src=$project_dir,dst=/project" \
    livara-assembler:0.1.0 /project/scripts/boot-smoke.py --firmware "$firmware" --timeout 1800 --capture-menus
 done
