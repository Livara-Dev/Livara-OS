#!/usr/bin/env bash
# An optional build CA is used only while this command runs and is then removed.
set -euo pipefail
temporary_ca=
cleanup() { [[ -z $temporary_ca ]] || rm -f -- "$temporary_ca"; }
trap cleanup EXIT
if [[ -s /run/secrets/livara_build_ca ]]; then
    temporary_ca=$(mktemp /tmp/livara-browser-build-ca.XXXXXX)
    cat /etc/ssl/certs/ca-certificates.crt /run/secrets/livara_build_ca > "$temporary_ca"
    export SSL_CERT_FILE=$temporary_ca REQUESTS_CA_BUNDLE=$temporary_ca CURL_CA_BUNDLE=$temporary_ca NODE_EXTRA_CA_CERTS=$temporary_ca
fi
"$@"
