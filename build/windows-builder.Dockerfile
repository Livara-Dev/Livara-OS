# syntax=docker/dockerfile:1
# The Windows entry point runs all Unix work on Linux Docker volumes.
FROM docker:27.5.1-cli AS client
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=client /usr/local/bin/docker /usr/local/bin/docker
COPY --from=client /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
RUN --mount=type=secret,id=proxy_ca \
    set -eu; \
    if [ -s /run/secrets/proxy_ca ]; then \
      printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99livara-build-ca; \
    fi; \
    apt-get update; apt-get install -y --no-install-recommends \
      bash make python3 python3-fonttools nodejs libharfbuzz-bin gnupg gpgv \
      dpkg tar xz-utils gzip coreutils findutils file ca-certificates; \
    apt-get clean; rm -rf /var/lib/apt/lists/*; \
    rm -f /etc/apt/apt.conf.d/99livara-build-ca
# Use the fork's pinned Node runtime: its TypeScript preference tests use native
# type stripping, which Ubuntu's older Node package does not support.
RUN --mount=type=bind,source=forks/code/upstream.json,target=/tmp/livara-node-pin.json,readonly \
    --mount=type=bind,source=scripts/windows-build.sh,target=/tmp/livara-windows-build,readonly \
    --mount=type=secret,id=proxy_ca <<'SH'
set -eu
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request

manifest = json.loads(Path('/tmp/livara-node-pin.json').read_text())
context = ssl.create_default_context()
certificate = Path('/run/secrets/proxy_ca')
if certificate.is_file() and certificate.stat().st_size:
    context.load_verify_locations(cafile=str(certificate))
archive = Path('/tmp/livara-node.tar.xz')
digest = hashlib.sha256()
size = 0
with urllib.request.urlopen(manifest['node_url'], context=context, timeout=120) as response, archive.open('wb') as output:
    for chunk in iter(lambda: response.read(1024 * 1024), b''):
        size += len(chunk)
        if size > 256 * 1024 * 1024:
            raise SystemExit('Pinned Node archive exceeded the size limit.')
        digest.update(chunk)
        output.write(chunk)
if digest.hexdigest() != manifest['node_sha256']:
    raise SystemExit('Pinned Node archive SHA-256 verification failed.')
PY
tar -xJf /tmp/livara-node.tar.xz -C /usr/local --strip-components=1
expected_node="$(python3 -c 'import json; print("v" + json.load(open("/tmp/livara-node-pin.json"))["node_version"])')"
test "$(node --version)" = "$expected_node"
rm /tmp/livara-node.tar.xz
install -m 0755 /tmp/livara-windows-build /usr/local/bin/livara-windows-build
sed -i 's/\r$//' /usr/local/bin/livara-windows-build
mkdir -p /project
SH
WORKDIR /project
ENTRYPOINT ["/usr/local/bin/livara-windows-build"]
