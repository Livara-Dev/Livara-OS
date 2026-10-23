#!/usr/bin/env bash
# Disposable GitHub-hosted VM only. Never run SDK cleanup on a developer machine.
set -euo pipefail
if [[ ${RUNNER_ENVIRONMENT:-} != github-hosted ]]; then
  echo 'ISO runner preparation requires a disposable GitHub-hosted runner.' >&2
  exit 1
fi
required_space=53687091200
free_space() { df --output=avail -B1 /var/lib/docker | tail -n 1; }
printf 'Initial Docker disk availability: %s bytes\n' "$(free_space)"
# Stop as soon as the actual assembly space requirement is met. Removing every
# cached SDK can spend several minutes deleting files the build never needs.
for sdk in /usr/local/lib/android /usr/share/dotnet /opt/hostedtoolcache /opt/ghc; do
  if (( $(free_space) >= required_space )); then break; fi
  [[ -d "$sdk" ]] || continue
  printf 'Reclaiming unused runner SDK: %s\n' "$sdk"
  if timeout --kill-after=15s 180s sudo rm -rf -- "$sdk"; then
    :
  else
    cleanup_status=$?
    if [[ $cleanup_status != 124 ]]; then exit "$cleanup_status"; fi
    echo 'SDK cleanup reached its time limit; checking the remaining disk space.'
  fi
  printf 'Docker disk availability: %s bytes\n' "$(free_space)"
done
if (( $(free_space) < required_space )); then
  echo 'At least 50 GiB free is required for ISO assembly and boot tests.' >&2
  exit 1
fi
sources_dir=$(mktemp -d)
trap 'rm -rf -- "$sources_dir"' EXIT
cat > "$sources_dir/ubuntu.list" <<'EOF'
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble main universe
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble-updates main universe
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu noble-security main universe
EOF
# Hosted runners may use mirror+file sources; rewriting an Azure URL in the
# .sources file does not replace those mirror lists. Use explicit signed Ubuntu
# sources for these build dependencies and leave unrelated repositories alone.
apt_options=(-o "Dir::Etc::SourceList=$sources_dir/ubuntu.list" -o Dir::Etc::SourceParts=-
  -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20)
echo 'Refreshing signed Ubuntu build dependencies (five-minute limit per command).'
timeout --kill-after=15s 300s sudo apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
timeout --kill-after=15s 300s sudo apt-get "${apt_options[@]}" install -y --no-install-recommends \
  python3-fonttools libharfbuzz-bin gnupg gpgv
df -h /var/lib/docker
