#!/usr/bin/env bash
set -euo pipefail

# Resolves monitor.py relative to this script when run from inside the repo.
# If you copy this script elsewhere (e.g. ~/bin), set HYDROTEMP_MONITOR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

: "${HYDROTEMP_MONITOR:=$SCRIPT_DIR/../../monitor.py}"
: "${HYDROTEMP_PYTHON:=python3}"
: "${HYDROTEMP_LOG_LEVEL:=INFO}"

if [ ! -f "$HYDROTEMP_MONITOR" ]; then
    echo "hydrotemp-start: monitor.py not found at $HYDROTEMP_MONITOR" >&2
    echo "Set HYDROTEMP_MONITOR to its full path, for example:" >&2
    echo "  HYDROTEMP_MONITOR=\$HOME/hardware-reversing/hydrotemp-aio/monitor.py $0" >&2
    exit 1
fi

exec "$HYDROTEMP_PYTHON" "$HYDROTEMP_MONITOR" --log-level "$HYDROTEMP_LOG_LEVEL"
