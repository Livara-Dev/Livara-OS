#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f /.dockerenv || ${EUID} != 0 || ${LIVARA_DISPOSABLE_GLASS_TEST:-} != 1 ]]; then
  echo 'Requires the disposable native renderer container.' >&2; exit 1
fi
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
package=${1:?Pass the actual desktop DEB}
dpkg-deb -x "$package" /
glib-compile-schemas /usr/share/glib-2.0/schemas
fc-cache -f /usr/share/fonts/truetype/livara
export LIVARA_COMPOSITOR_PROBE=native LIVARA_INSTALLED_PACKAGE_TEST=1
exec bash "$project/scripts/test-liquid-glass.sh"
