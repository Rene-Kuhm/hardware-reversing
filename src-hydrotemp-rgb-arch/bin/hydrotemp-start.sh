#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(dirname "$(readlink -f "$0")")/.."
exec python3 "${INSTALL_DIR}/monitor.py" --log-level INFO