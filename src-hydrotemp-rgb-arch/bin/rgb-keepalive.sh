#!/usr/bin/env bash
set -euo pipefail

DEVICE_ID="${RGB_DEVICE_ID:-1}"
MEMORY_DEVICE_ID="${RGB_MEMORY_DEVICE_ID:-0}"
COLOR="${RGB_COLOR:-FFFFFF}"
MODE="${RGB_MODE:-static}"
INTERVAL="${RGB_INTERVAL_SEC:-20}"
BRIGHTNESS="${RGB_BRIGHTNESS:-100}"
ARGB_SIZE="${RGB_ARG_SIZE:-30}"

apply_rgb() {
  openrgb --noautoconnect --device "${MEMORY_DEVICE_ID}" --mode "${MODE}" --color "${COLOR}" --brightness "${BRIGHTNESS}" >/dev/null 2>&1 || \
    openrgb --noautoconnect --device "${MEMORY_DEVICE_ID}" --mode direct --color "${COLOR}" >/dev/null 2>&1 || true

  openrgb --noautoconnect --device "${DEVICE_ID}" --mode "${MODE}" --color "${COLOR}" --brightness "${BRIGHTNESS}" >/dev/null 2>&1 || \
    openrgb --noautoconnect --device "${DEVICE_ID}" --mode direct --color "${COLOR}" >/dev/null 2>&1 || true

  for zone in 0 1 2 3; do
    if [[ "${zone}" == 1 || "${zone}" == 2 ]]; then
      openrgb --noautoconnect --device "${DEVICE_ID}" --zone "${zone}" --size "${ARGB_SIZE}" >/dev/null 2>&1 || true
    fi
    openrgb --noautoconnect --device "${DEVICE_ID}" --zone "${zone}" --mode "${MODE}" --color "${COLOR}" --brightness "${BRIGHTNESS}" >/dev/null 2>&1 || true
  done
}

apply_rgb
while true; do
  sleep "${INTERVAL}"
  apply_rgb
done
