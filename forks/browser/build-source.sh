#!/usr/bin/env bash
# MPL-2.0. Full native Linux x86_64 browser compilation, not an artifact build.
set -euo pipefail
fork_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$fork_dir/../.." && pwd)
work_dir=${1:-$project_dir/.build/browser-source}
artifact_dir=${2:-$project_dir/dist/forks}
jobs=${LIVARA_BUILD_JOBS:-4}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'LIVARA_BUILD_JOBS must be a positive integer' >&2; exit 2; }
[[ $(uname -m) == x86_64 ]] || { echo 'Livara Browser requires an x86_64 Linux build host.' >&2; exit 2; }
mkdir -p "$work_dir" "$artifact_dir"
python3 - "$work_dir" <<'PY'
import shutil,sys
free=shutil.disk_usage(sys.argv[1]).free
if free < 30*1024**3:
    raise SystemExit('Full Firefox/Zen source compilation requires at least 30 GiB free in the browser work volume; 80–100 GiB is recommended for the complete OS pipeline.')
PY
readarray -t pinned < <(python3 - "$fork_dir/upstream.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]));print(m['upstream']);print(m['commit']);print(m['tag']);print(m['firefox']['source_url']);print(m['firefox']['sha512'])
PY
)
checkout=$work_dir/zen
if [[ ! -d "$checkout/.git" ]]; then
    git clone --depth=1 --branch "${pinned[2]}" --filter=blob:none "${pinned[0]}" "$checkout"
fi
[[ $(git -C "$checkout" rev-parse HEAD) == "${pinned[1]}" ]] || { echo 'Browser source cache has an unexpected revision. Use a separate clean work volume.' >&2; exit 1; }
python3 "$fork_dir/prepare.py" "$checkout"
cd "$checkout"
export GIT_AUTHOR_NAME='Livara Build'
export GIT_AUTHOR_EMAIL='build@localhost'
export GIT_COMMITTER_NAME=$GIT_AUTHOR_NAME
export GIT_COMMITTER_EMAIL=$GIT_AUTHOR_EMAIL
export ZEN_RELEASE=1 ZEN_GA_DISABLE_PGO=1 ZEN_DISABLE_LTO=1 SURFER_COMPAT=x86_64
export MOZ_NOSPAM=1 MOZBUILD_STATE_PATH=${MOZBUILD_STATE_PATH:-/home/builder/.mozbuild}
npm ci --no-audit --no-fund
npm run surfer -- ci --brand release --display-version 1.23.4b
# Surfer reuses this verified archive, rather than fetching unchecked source.
source_name=${pinned[3]##*/}
mkdir -p .surfer/engine
source_path=$checkout/.surfer/engine/$source_name
if [[ ! -f "$source_path" ]]; then
    curl --fail --location --retry 3 --connect-timeout 30 "${pinned[3]}" --output "$source_path.part"
    mv -- "$source_path.part" "$source_path"
fi
if ! printf '%s  %s\n' "${pinned[4]}" "$source_path" | sha512sum --check --status; then
    echo 'Pinned Firefox source checksum failed. The cached source was not compiled.' >&2
    exit 1
fi
npm run download
# The pinned upstream import script generates native/static prefs, merges its
# checked-in search dumps, imports all Zen patches and copies Livara chrome.
npm run import
# Surfer emits upstream URLs in its generated branding prefs; replace that
# generated source with Livara's maintained branded defaults before compiling.
install -m 0644 "$fork_dir/branding-pref.js" engine/browser/branding/release/pref/firefox-branding.js
cd engine
./mach --no-interactive bootstrap --application-choice browser --no-system-changes
cd ..
npm run build -- --jobs "$jobs"
cd engine
./mach package
cd ..
python3 "$fork_dir/package-build.py" "$checkout/engine/obj-livara/dist" "$artifact_dir"
printf 'Built from pinned source: %s/livara-browser-linux-x64.tar.xz\n' "$artifact_dir"
