#!/usr/bin/env bash
# Windows Docker Desktop driver. Never use a container path as a host bind source.
set -euo pipefail

mode="${1:-}"
case "$mode" in check|build|export) ;; *) echo 'Usage: livara-windows-build check|build|export' >&2; exit 2 ;; esac

if [[ "$mode" == export ]]; then
  test -d /export || { echo 'The Windows output folder must be mounted at /export.' >&2; exit 1; }
  copied=0
  for name in livara-desktop_0.1.0_all.deb livara-os-0.1.0-amd64.iso livara-os-0.1.0-amd64.iso.sha256 livara-os-0.1.0-packages.txt CHECK-RESULT.txt; do
    if [[ -f "/output/$name" ]]; then
      cp -- "/output/$name" "/export/$name"
      copied=$((copied + 1))
    fi
  done
  ((copied > 0)) || { echo 'No completed build products were available to copy.' >&2; exit 1; }
  # A check run can share a Windows dist folder with an earlier full build.
  # Verify only the ISO and checksum copied from this run's output volume.
  if [[ -f /output/livara-os-0.1.0-amd64.iso && -f /output/livara-os-0.1.0-amd64.iso.sha256 ]]; then
    (cd /export && sha256sum --check livara-os-0.1.0-amd64.iso.sha256)
  fi
  printf 'Copied %s completed build products to Windows.\n' "$copied"
  exit 0
fi

for name in LIVARA_SOURCE_VOLUME LIVARA_BUILD_VOLUME LIVARA_OUTPUT_VOLUME LIVARA_BUILD_ID; do
  value="${!name:-}"
  [[ "$value" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo "Missing or invalid $name" >&2; exit 2; }
done
[[ "${LIVARA_BUILD_JOBS:-2}" =~ ^([1-9]|1[0-6])$ ]] || { echo 'LIVARA_BUILD_JOBS must be between 1 and 16.' >&2; exit 2; }
test -f /source/packaging/build-deb.sh || { echo 'The extracted source package must be mounted at /source.' >&2; exit 1; }
for program in docker python3 make dpkg-deb tar gzip sha256sum; do
  command -v "$program" >/dev/null || { echo "Builder dependency missing: $program" >&2; exit 1; }
done
docker_cmd=(env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock)
docker_host="$("${docker_cmd[@]}" info --format '{{.OSType}}/{{.Architecture}}')"
case "$docker_host" in linux/x86_64|linux/amd64) ;; *) echo 'The builder needs an x86_64 Linux Docker engine.' >&2; exit 1 ;; esac
if [[ "$mode" == build ]]; then
  engine_memory="$("${docker_cmd[@]}" info --format '{{.MemTotal}}')"
  engine_cpus="$("${docker_cmd[@]}" info --format '{{.NCPU}}')"
  # Docker reports usable RAM, slightly below the configured WSL allocation.
  memory_gib=$(((engine_memory + 512 * 1024 * 1024) / (1024 * 1024 * 1024)))
  if ((memory_gib < 16)); then
    echo 'Compiling the VS Code and Zen forks needs at least 16 GiB RAM allocated to Docker Desktop; 24 GiB or more is recommended.' >&2
    exit 1
  fi
  # Leave 8 GiB for linking/system work and budget 4 GiB per compile worker.
  memory_jobs=$(((memory_gib - 8) / 4))
  effective_jobs="${LIVARA_BUILD_JOBS:-2}"
  ((effective_jobs <= engine_cpus)) || effective_jobs="$engine_cpus"
  ((effective_jobs <= memory_jobs)) || effective_jobs="$memory_jobs"
  export LIVARA_BUILD_JOBS="$effective_jobs"
  printf 'Using %s build workers within Docker CPU/RAM limits (portable x86-64 target).\n' "$LIVARA_BUILD_JOBS"
fi

# Only project material is copied. Existing ISOs, credentials, .git and caches stay out.
mkdir -p /project /build /output
find /project -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
source_entries=()
for entry in README.md LICENSE Makefile pyproject.toml .gitignore .dockerignore .gitattributes Build-Livara.bat Build-Livara.ps1 .github artwork build docs fonts forks packaging scripts share src tests; do
  [[ ! -e "/source/$entry" ]] || source_entries+=("$entry")
done
copy_excludes=(
  --exclude='.git' --exclude='.build' --exclude='dist' --exclude='__pycache__'
  --exclude='*.pyc' --exclude='*.pyo' --exclude='*.log' --exclude='*.egg-info'
  --exclude='.cache' --exclude='.pytest_cache' --exclude='.mypy_cache' --exclude='.ruff_cache'
  --exclude='.venv' --exclude='venv' --exclude='node_modules' --exclude='.npm' --exclude='.yarn' --exclude='.mozbuild'
  --exclude='forks/*/vendor' --exclude='forks/*/third_party'
  --exclude='.env' --exclude='.env.*' --exclude='*.pem' --exclude='*.key' --exclude='*.p12' --exclude='*.pfx'
  --exclude='.ssh' --exclude='.gnupg' --exclude='.aws' --exclude='.azure' --exclude='.docker' --exclude='.kube'
  --exclude='.config' --exclude='.codex' --exclude='secrets' --exclude='.secrets' --exclude='credentials'
  --exclude='.netrc' --exclude='_netrc' --exclude='.npmrc' --exclude='.pypirc'
  --exclude='credentials.json' --exclude='service-account.json' --exclude='id_rsa' --exclude='id_ed25519'
  --exclude='*.iso' --exclude='*.iso.*' --exclude='*.deb' --exclude='kali-core*.tar*'
)
tar -C /source "${copy_excludes[@]}" -cf - "${source_entries[@]}" | tar -C /project --no-same-owner -xf -
python3 - <<'PY'
from pathlib import Path
root = Path('/project')
for path in root.rglob('*'):
    if path.is_symlink():
        continue
    if path.is_dir():
        path.chmod(0o755)
        continue
    if not path.is_file():
        continue
    with path.open('rb') as stream:
        shebang = stream.read(2) == b'#!'
    unix_source = (path.suffix in ('.sh', '.bash', '.py', '.service', '.desktop', '.xml', '.override')
                   or 'Dockerfile' in path.name or path.name == 'mozconfig' or shebang)
    if unix_source:
        data = path.read_bytes()
        if b'\r\n' in data:
            path.write_bytes(data.replace(b'\r\n', b'\n'))
    # NTFS bind modes cannot make the nested Docker CLI helper executable.
    path.chmod(0o755 if path.suffix == '.sh' or shebang else 0o644)
PY
cd /project
if [[ "$mode" == build ]]; then
  # Check browser compiler access before spending hours compiling the editor.
  python3 forks/browser/prepare-toolchains.py --check
fi
printf 'Rebuilding Livara font binaries from the editable UFO sources...\n'
python3 scripts/build-fonts.py
printf 'Validating local VS Code and Zen fork recipes without downloads...\n'
bash scripts/build-code.sh --check
bash scripts/build-browser.sh --check
python3 scripts/prepare-tor-browser.py --check
printf 'Checking Livara source and building its desktop package...\n'
make check
bash packaging/build-deb.sh /output
if [[ "$mode" == check ]]; then
  printf 'Livara OS 0.1.0 local source/recipe checks and Linux desktop packaging passed.\nThe VS Code and Zen forks were not downloaded or compiled.\nThe official Tor Browser bundle was not downloaded.\nNo live root filesystem, Kali image, or ISO was built.\n' > /output/CHECK-RESULT.txt
  cat /output/CHECK-RESULT.txt
  exit 0
fi

available_bytes="$(df -B1 --output=avail /build | tail -1 | tr -d ' ')"
if ((available_bytes < 100 * 1024 * 1024 * 1024)); then
  echo 'A full build including VS Code and Zen source compilation needs at least 100 GiB free inside Docker Desktop; 150 GiB or more is recommended.' >&2
  echo 'Increase the Docker Desktop disk image limit or free space, then run the builder again.' >&2
  exit 1
fi
mkdir -p /project/dist
cp /output/livara-desktop_0.1.0_all.deb /project/dist/
mkdir -p /project/dist/forks
printf 'Compiling Livara Code from its pinned VS Code source...\n'
bash scripts/build-code.sh /project/dist/forks
test -s /project/dist/forks/livara-code-linux-x64.tar.xz
printf 'Compiling Livara Browser from its pinned Zen source...\n'
bash scripts/build-browser.sh /project/dist/forks
test -s /project/dist/forks/livara-browser-linux-x64.tar.xz
printf 'Downloading and verifying the unchanged official Tor Browser bundle...\n'
python3 scripts/prepare-tor-browser.py /project/dist/forks
test -s /project/dist/forks/livara-tor-browser-linux-x64.tar.xz
printf 'Both source-built applications and the verified official Tor Browser bundle are ready for the live filesystem.\n'
build_args=(--build-arg "LIVARA_APT_REFRESH=$(date -u +%Y-%m-%d)")
if [[ -n "${LIVARA_BUILD_CA:-}" ]]; then
  test -s "$LIVARA_BUILD_CA" || { echo 'The supplied build CA bundle is missing or empty.' >&2; exit 1; }
  build_args+=(--secret "id=proxy_ca,src=$LIVARA_BUILD_CA")
fi
# Docker Desktop injects its configured proxy environment into this controller.
# Forward the predefined build arguments by name, without logging their values.
for name in HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY http_proxy https_proxy no_proxy all_proxy; do
  [[ -z "${!name:-}" ]] || build_args+=(--build-arg "$name")
done
rootfs_container=''
cleanup() {
  [[ -z "$rootfs_container" ]] || "${docker_cmd[@]}" rm -f "$rootfs_container" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'Building the offline Kali core image...\n'
"${docker_cmd[@]}" build "${build_args[@]}" -t localhost/livara-kali:0.1.0-core -f share/livara/toolbox/Containerfile share/livara/toolbox
"${docker_cmd[@]}" save localhost/livara-kali:0.1.0-core | gzip -1 > /output/kali-core.tar.gz
printf 'Building the live desktop and ISO assembly tools...\n'
"${docker_cmd[@]}" build "${build_args[@]}" --iidfile /tmp/livara-rootfs.iid --target rootfs -t livara-rootfs:0.1.0 -f build/Dockerfile .
"${docker_cmd[@]}" build "${build_args[@]}" --iidfile /tmp/livara-assembler.iid --target assembler -t livara-assembler:0.1.0 -f build/Dockerfile .
rootfs_image="$(cat /tmp/livara-rootfs.iid)"
assembler_image="$(cat /tmp/livara-assembler.iid)"
rootfs_container="$("${docker_cmd[@]}" create --label "org.livara.build=$LIVARA_BUILD_ID" "$rootfs_image")"
printf 'Exporting the Linux filesystem with Unix ownership and permissions...\n'
"${docker_cmd[@]}" run --rm --label "org.livara.build=$LIVARA_BUILD_ID" --entrypoint bash \
  --mount "type=volume,source=$LIVARA_BUILD_VOLUME,target=/build" \
  "$assembler_image" -c 'mkdir -p /build/rootfs; find /build/rootfs -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
"${docker_cmd[@]}" export "$rootfs_container" | \
  "${docker_cmd[@]}" run --rm -i --label "org.livara.build=$LIVARA_BUILD_ID" --entrypoint tar \
    --mount "type=volume,source=$LIVARA_BUILD_VOLUME,target=/build" \
    "$assembler_image" -xpf - -C /build/rootfs
"${docker_cmd[@]}" rm "$rootfs_container" >/dev/null
rootfs_container=''
"${docker_cmd[@]}" run --rm --label "org.livara.build=$LIVARA_BUILD_ID" --entrypoint bash \
  --mount "type=volume,source=$LIVARA_BUILD_VOLUME,target=/build" \
  --mount "type=volume,source=$LIVARA_OUTPUT_VOLUME,target=/output" \
  "$assembler_image" -c 'install -m 0644 /output/kali-core.tar.gz /build/rootfs/usr/share/livara/toolbox/'
printf 'Creating the local Livara ISO...\n'
"${docker_cmd[@]}" run --rm --label "org.livara.build=$LIVARA_BUILD_ID" \
  --mount "type=volume,source=$LIVARA_SOURCE_VOLUME,target=/project,readonly" \
  --mount "type=volume,source=$LIVARA_BUILD_VOLUME,target=/build" \
  --mount "type=volume,source=$LIVARA_OUTPUT_VOLUME,target=/output" \
  -e "LIVARA_BUILD_JOBS=${LIVARA_BUILD_JOBS:-2}" \
  "$assembler_image"
test -s /output/livara-os-0.1.0-amd64.iso
(cd /output && sha256sum --check livara-os-0.1.0-amd64.iso.sha256)
printf 'Local build finished. Copying the result back to Windows is the final step.\n'
