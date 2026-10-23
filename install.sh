#!/usr/bin/env bash
set -euo pipefail
setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

bootstrap=0
assume_yes=0
dry_run=0
setup_args=()
for argument in "$@"; do
  case "$argument" in
    --install-prerequisites) bootstrap=1 ;;
    --yes) assume_yes=1 ;;
    --dry-run) dry_run=1; setup_args+=("$argument") ;;
    *) setup_args+=("$argument") ;;
  esac
done

if [[ "$(uname -s)" != Linux ]]; then
  echo 'linux-setup supports Linux only. Use a Linux distribution inside WSL on Windows.' >&2
  exit 1
fi

if (( bootstrap )); then
  # /etc/os-release is the distribution-owned identification file.
  ID=''
  ID_LIKE=''
  [[ ! -r /etc/os-release ]] || source /etc/os-release
  if [[ " $ID $ID_LIKE " != *' debian '* && " $ID $ID_LIKE " != *' ubuntu '* ]]; then
    echo 'Automatic prerequisite installation supports Ubuntu/Debian. Install Python 3.9+, Git, curl, and CA certificates using your distribution package manager.' >&2
    exit 1
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo 'apt-get is required for Ubuntu/Debian prerequisite installation.' >&2
    exit 1
  fi
  administrator=()
  if (( EUID != 0 )); then
    administrator=(sudo)
  fi
  printf '%s\n' 'Prerequisite installation uses administrative access and changes system packages:'
  printf '  %sapt-get update\n' "${administrator[*]:+${administrator[*]} }"
  printf '  %sapt-get install --no-install-recommends python3 git curl ca-certificates\n' "${administrator[*]:+${administrator[*]} }"
  if (( ! dry_run )); then
    if (( ! assume_yes )); then
      if [[ ! -t 0 ]]; then
        echo 'Run interactively to confirm, or add --yes to authorize the displayed prerequisite commands.' >&2
        exit 1
      fi
      read -r -p 'Install these prerequisites? [y/N] ' answer
      [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]] || exit 0
    fi
    if (( EUID != 0 )) && ! command -v sudo >/dev/null 2>&1; then
      echo 'sudo is unavailable. Ask an administrator to run the displayed commands, then rerun ./install.sh.' >&2
      exit 1
    fi
    "${administrator[@]}" apt-get update
    "${administrator[@]}" apt-get install -y --no-install-recommends python3 git curl ca-certificates
  fi
elif (( assume_yes )); then
  echo '--yes is only used with --install-prerequisites by install.sh.' >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))'; then
  if (( bootstrap && dry_run )); then
    echo 'Dry run: Python 3.9+ is required before the remaining installation can be planned.'
    exit 0
  fi
  echo 'Python 3.9+ is required. On Ubuntu/Debian run ./install.sh --install-prerequisites; on other Linux distributions install it with your package manager.' >&2
  exit 1
fi
exec python3 "$setup_dir/scripts/setup.py" "${setup_args[@]}"
