#!/usr/bin/env bash
# Build the actual pinned Livara fork of the open-source editor.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == --check ]]; then
  python3 - "$project_dir" <<'PY'
import json, pathlib, re, sys
root=pathlib.Path(sys.argv[1]); pin=json.loads((root/'forks/code/upstream.json').read_text())
assert re.fullmatch('[0-9a-f]{40}',pin['commit'])
assert re.fullmatch('[0-9a-f]{64}',pin['source_sha256'])
assert pin['commit'] in pin['source_url']
for path in ('forks/code/apply.py','forks/code/patches/0002-standalone-build.patch','forks/code/overlay/core/livara.contribution.ts','forks/code/overlay/core/windowControls.ts','forks/code/test-window-controls.mjs','forks/code/overlay/onboarding/welcomeOnboarding.contribution.ts','forks/code/overlay/extension/package.json','build/Dockerfile.code','scripts/prepare-code-headers.py','forks/code/native-headers.json'):
    assert (root/path).is_file(), path
json.loads((root/'forks/code/overlay/extension/themes/livara-amoled.json').read_text())
print('Livara Code source recipe, source pin and theme checks passed; no download or compilation.')
PY
  exit 0
fi

if [[ "${1:-}" == --compile || "${1:-}" == --dependencies || "${1:-}" == --assemble || "${1:-}" == --resume || "${1:-}" == --finish ]]; then
  build_mode="$1"
  # This path runs ONLY inside the Linux Docker build stage.
  project_dir="${2:?project directory required}"
  work_dir="${3:?work directory required}"
  output_dir="${4:?artifact directory required}"
  [[ "$work_dir" == /* && "$work_dir" != / ]] || { echo 'Use an absolute dedicated work directory.' >&2; exit 2; }
  [[ "${LIVARA_BUILD_JOBS:-2}" =~ ^([1-9]|1[0-6])$ ]] || { echo 'LIVARA_BUILD_JOBS must be between 1 and 16.' >&2; exit 2; }
  export LIVARA_BUILD_JOBS="${LIVARA_BUILD_JOBS:-2}"
  export LIVARA_SOURCE_DATE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit_date"])' "$project_dir/forks/code/upstream.json")"
  export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 FOUNDRY_LOCAL_SKIP_INSTALL=1 NODE_USE_ENV_PROXY=1
  source_dir="$work_dir/code"
  mkdir -p "$work_dir" "$output_dir"
  if [[ "$build_mode" != --assemble && "$build_mode" != --finish ]]; then
  if [[ "$build_mode" != --resume ]]; then
  test ! -e "$source_dir" || { echo 'Refusing to overwrite an existing code source checkout.' >&2; exit 1; }
  source_url="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_url"])' "$project_dir/forks/code/upstream.json")"
  source_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_sha256"])' "$project_dir/forks/code/upstream.json")"
  export BUILD_SOURCEVERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$project_dir/forks/code/upstream.json")"
  curl --fail --location --retry 3 --output "$work_dir/code-source.tar.gz" "$source_url"
  printf '%s  %s\n' "$source_sha" "$work_dir/code-source.tar.gz" | sha256sum --check -
  mkdir "$source_dir"
  tar -xzf "$work_dir/code-source.tar.gz" -C "$source_dir" --strip-components=1
  patch --batch --forward -p1 -d "$source_dir" < "$project_dir/forks/code/patches/0002-standalone-build.patch"
  fi
  cd "$source_dir"
  git init --quiet
  git config user.name 'Livara local source build'
  git config user.email 'build@localhost'
  # Upstream npm postinstall requires repository configuration. Build identity is the locked source SHA.
  export ELECTRON_SKIP_BINARY_DOWNLOAD=1 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 FOUNDRY_LOCAL_SKIP_INSTALL=1
  # Node24 supports inherited HTTP(S) proxies for installer scripts that use its global agent.
  export NODE_USE_ENV_PROXY=1
  export npm_config_jobs="$LIVARA_BUILD_JOBS"
  export CFLAGS='-O2 -march=x86-64 -mtune=generic'
  export CXXFLAGS='-O2 -march=x86-64 -mtune=generic'
  # Avoid oversubscribing native installs on laptops and small Docker Desktop VMs.
  python3 - "$source_dir/build/npm/postinstall.ts" <<'PY2'
from pathlib import Path
import sys
p=Path(sys.argv[1]); text=p.read_text(); old='const concurrency = Math.min(os.cpus().length, 8);'
assert text.count(old)==1 or 'LIVARA_BUILD_JOBS' in text
p.write_text(text.replace(old, "const concurrency = Math.min(os.cpus().length, Math.max(1, Math.min(16, Number(process.env['LIVARA_BUILD_JOBS']) || 2)));"))
PY2
  # Native packages must not each fetch Electron/Node headers through their
  # own single-attempt TLS client. Prime all targets from verified local archives.
  export npm_config_devdir="$work_dir/node-gyp"
  python3 "$project_dir/scripts/prepare-code-headers.py" \
    --manifest "$project_dir/forks/code/native-headers.json" \
    --source "$source_dir" --cache "$npm_config_devdir"
  export npm_config_fetch_retries=5 npm_config_fetch_retry_mintimeout=2000
  export npm_config_fetch_retry_maxtimeout=30000 npm_config_fetch_timeout=180000
  npm ci --no-audit --no-fund
  fi
  if [[ "$build_mode" == --dependencies ]]; then exit 0; fi
  patch_args=()
  [[ "$build_mode" != --finish ]] || patch_args+=(--refresh)
  python3 "$project_dir/forks/code/apply.py" "$source_dir" --project "$project_dir" "${patch_args[@]}"
  cd "$source_dir"
  export BUILD_SOURCEVERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$project_dir/forks/code/upstream.json")"
  export npm_config_jobs="$LIVARA_BUILD_JOBS"
  export CFLAGS='-O2 -march=x86-64 -mtune=generic'
  export CXXFLAGS='-O2 -march=x86-64 -mtune=generic'
  node --test "$project_dir/forks/code/test-features.cjs"
  node --test "$project_dir/forks/code/test-window-controls.mjs"
  npm run gulp -- vscode-linux-x64-min
  built_dir="$work_dir/VSCode-linux-x64"
  test -x "$built_dir/livara-code"
  test -x "$built_dir/bin/livara-code"
  test -f "$built_dir/resources/app/extensions/livara-workbench/package.json"
  install -d "$built_dir/resources/app/livara/fonts" "$built_dir/resources/app/out/vs/livara/fonts"
  for font in "$project_dir"/fonts/ttf/Livara*.ttf; do
    test -f "$font" || { echo 'The Livara font sources were not supplied.' >&2; exit 1; }
    install -m 0644 "$font" "$built_dir/resources/app/livara/fonts/"
    install -m 0644 "$font" "$built_dir/resources/app/out/vs/livara/fonts/"
  done
  install -m 0644 "$project_dir/fonts/OFL.txt" "$built_dir/resources/app/livara/fonts/OFL-Livara.txt"
  install -m 0644 "$project_dir/fonts/vendor/vazirmatn/OFL.txt" "$built_dir/resources/app/livara/fonts/OFL-Vazirmatn.txt"
  install -m 0644 "$project_dir/fonts/README.md" "$built_dir/resources/app/livara/fonts/README.md"
  install -m 0644 "$project_dir/forks/code/LICENSE" "$built_dir/resources/app/livara/LICENSE-Livara.txt"
  python3 - "$source_dir/livara-source.json" "$built_dir/resources/app/livara-build.json" <<'PY'
import json,pathlib,sys
report=json.loads(pathlib.Path(sys.argv[1]).read_text()); report['built']=True
report['build_target']='vscode-linux-x64-min'; report['distribution']='Livara Code'
pathlib.Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
PY
  find "$built_dir" -type d -exec chmod a+rx {} +
  find "$built_dir" -type f -exec chmod a+r {} +
  mv "$built_dir" "$work_dir/livara-code"
  cp "$work_dir/livara-code/resources/app/livara-build.json" "$output_dir/livara-code-build.json"
  XZ_OPT="-T${LIVARA_BUILD_JOBS:-2} -3" tar -C "$work_dir" -cJf "$output_dir/.livara-code-linux-x64.tar.xz.partial" livara-code
  mv -- "$output_dir/.livara-code-linux-x64.tar.xz.partial" "$output_dir/livara-code-linux-x64.tar.xz"
  (cd "$output_dir" && sha256sum livara-code-linux-x64.tar.xz > livara-code-linux-x64.tar.xz.sha256)
  printf 'Built Livara Code from the pinned open-source checkout.\n'
  exit 0
fi

output_dir="${1:-$project_dir/dist/forks}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
docker_cmd=("$project_dir/scripts/docker-local.sh")
engine="$("${docker_cmd[@]}" info --format '{{.OSType}}/{{.Architecture}}')"
case "$engine" in linux/amd64|linux/x86_64) ;; *) echo 'Livara Code requires an x86_64 Linux Docker engine.' >&2; exit 1 ;; esac
build_args=(--build-arg "LIVARA_BUILD_JOBS=${LIVARA_BUILD_JOBS:-2}")
if [[ -n "${LIVARA_BUILD_CA:-}" ]]; then
  test -s "$LIVARA_BUILD_CA" || { echo 'LIVARA_BUILD_CA is missing or empty.' >&2; exit 1; }
  build_args+=(--secret "id=proxy_ca,src=$LIVARA_BUILD_CA")
elif [[ -n "${CODEX_PROXY_CERT:-}" && -s /etc/ssl/certs/ca-certificates.crt ]]; then
  build_args+=(--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt)
fi
for name in HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY http_proxy https_proxy no_proxy all_proxy; do
  [[ -z "${!name:-}" ]] || build_args+=(--build-arg "$name")
done
build_id="${LIVARA_BUILD_ID:-local}"
[[ "$build_id" =~ ^[a-zA-Z0-9_.-]+$ ]] || { echo 'Invalid LIVARA_BUILD_ID.' >&2; exit 2; }
code_version="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$project_dir/forks/code/upstream.json")"
image="livara-code-artifact:$code_version-$build_id"
"${docker_cmd[@]}" build "${build_args[@]}" --target artifact --label "org.livara.build=$build_id" -f "$project_dir/build/Dockerfile.code" -t "$image" "$project_dir"
container_id="$("${docker_cmd[@]}" create --label "org.livara.build=$build_id" "$image" /unused)"
cleanup() { "${docker_cmd[@]}" rm -f "$container_id" >/dev/null 2>&1 || true; }
trap cleanup EXIT
for name in livara-code-linux-x64.tar.xz livara-code-linux-x64.tar.xz.sha256 livara-code-build.json; do
  "${docker_cmd[@]}" cp "$container_id:/artifacts/$name" "$output_dir/$name"
done
(cd "$output_dir" && sha256sum --check livara-code-linux-x64.tar.xz.sha256)
printf 'Livara Code is ready in %s\n' "$output_dir"
