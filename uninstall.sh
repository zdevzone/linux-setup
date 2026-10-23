#!/usr/bin/env bash
set -euo pipefail
setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo 'Uninstallation requires Python 3.9 or newer.' >&2
  exit 1
fi
exec python3 "$setup_dir/scripts/uninstall.py" "$@"
