#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --check ]]; then
    python3 "$project_dir/forks/browser/check-source.py"
    for script in "$project_dir/scripts/build-browser.sh" "$project_dir/forks/browser/build-source.sh" "$project_dir/forks/browser/with-build-trust.sh"; do
        bash -n "$script"
    done
    exit 0
fi
output_dir=${1:-$project_dir/dist/forks}
mkdir -p "$output_dir"
output_dir=$(cd -- "$output_dir" && pwd)
docker_cmd=$project_dir/scripts/docker-local.sh
jobs=${LIVARA_BUILD_JOBS:-4}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'LIVARA_BUILD_JOBS must be a positive integer' >&2; exit 2; }
image=livara-browser-source-build:local
build_id=${LIVARA_BUILD_ID:-local}
arguments=(build --target artifact --file "$project_dir/build/Dockerfile.browser" --tag "$image" --build-arg "LIVARA_BUILD_JOBS=$jobs" --label "org.livara.build=$build_id")
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
    [[ -z ${!name:-} ]] || arguments+=(--build-arg "$name")
done
if [[ -n ${LIVARA_BUILD_CA:-} ]]; then
    [[ -f $LIVARA_BUILD_CA ]] || { echo 'LIVARA_BUILD_CA must name an existing certificate file' >&2; exit 2; }
    arguments+=(--secret "id=livara_build_ca,src=$LIVARA_BUILD_CA")
elif [[ -n ${CODEX_PROXY_CERT:-} && -s /etc/ssl/certs/ca-certificates.crt ]]; then
    arguments+=(--secret id=livara_build_ca,src=/etc/ssl/certs/ca-certificates.crt)
fi
log_dir=${LIVARA_BROWSER_LOG_DIR:-$output_dir/logs}
mkdir -p "$log_dir"
log_path="$log_dir/browser-build-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
printf 'Compiling the full browser; persistent log: %s\n' "$log_path"
if ! "$docker_cmd" "${arguments[@]}" "$project_dir" 2>&1 | tee "$log_path"; then
    printf 'Browser compilation failed. Full log retained at %s. Existing compiler caches were preserved.\n' "$log_path" >&2
    exit 1
fi
container=$("$docker_cmd" create --label "org.livara.build=$build_id" "$image" /not-executed)
cleanup() { "$docker_cmd" rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
artifact=livara-browser-linux-x64.tar.xz
"$docker_cmd" cp "$container:/artifacts/$artifact" "$output_dir/$artifact.part"
mv -- "$output_dir/$artifact.part" "$output_dir/$artifact"
"$docker_cmd" cp "$container:/artifacts/$artifact.sha256" "$output_dir/$artifact.sha256"
(cd "$output_dir" && sha256sum --check "$artifact.sha256")
printf 'Livara Browser source-build artifact: %s/%s\n' "$output_dir" "$artifact"
