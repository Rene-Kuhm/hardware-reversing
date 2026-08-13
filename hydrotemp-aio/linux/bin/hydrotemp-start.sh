#!/usr/bin/env bash
set -euo pipefail

exec /home/tecnodespegue/.venv-hw/bin/python /home/tecnodespegue/Datos-xyz-hydrotemp/monitor.py --log-level INFO
