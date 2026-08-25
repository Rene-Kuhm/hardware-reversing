#!/usr/bin/env bash
# Aplica color sólido a:
#   - Z790 AORUS ELITE AX (chip IT5701)
#   - HyperX Fury RGB (RAM)
# detectados por OpenRGB en este sistema.
#
# OpenRGB no soporta múltiples -d -z en la misma línea, así que iteramos.
# Las zonas D_LED1/D_LED2 de la motherboard reportan 0 LEDs por defecto
# (firmware IT5701 no lee el chain length); forzamos --size 16 con el
# típico HydroTemp AIO (2 fans ARGB de 8 c/u, o 1 fan de 16).
set -uo pipefail

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

export QT_QPA_PLATFORM=offscreen
export LIBGL_ALWAYS_SOFTWARE=1
export HOME=/root
export XDG_CONFIG_HOME=/root/.config

# OpenRGB intenta crear ~/.config/OpenRGB al primer arranque. Creamos el
# directorio explícitamente para que no crashee con filesystem_error cuando
# corre como user que no es root.
mkdir -p /root/.config/OpenRGB

OPENRGB="/home/tecnodespegue/.nix-profile/bin/openrgb"
COLOR="${RGB_COLOR:-FFFFFF}"
BRIGHTNESS="${RGB_BRIGHTNESS:-100}"
MODE="${RGB_MODE:-Static}"

# Lista hardcoded de devices + zonas para la Z790 AORUS ELITE AX + HyperX.
# Layout conocido:
#   Device 0: HyperX Fury RGB
#     zone 0: HyperX Slot 1 (5 LEDs)
#     zone 1: HyperX Slot 2 (5 LEDs)
#   Device 1: Z790 AORUS ELITE AX (IT5701)
#     zone 0: D_LED1       → header ARGB 1 (AIO fans) — size forzado
#     zone 1: D_LED2       → header ARGB 2            — size forzado
#     zone 2: LED_C1       → LEDs físicos
#     zone 3: Chipset Accent
#     zone 4: LED_C2
log "=== Aplicando $MODE $COLOR brillo=$BRIGHTNESS a todos los devices ==="

# --- HyperX RAM (device 0) ---
for zone in 0 1; do
    log "device 0 (HyperX) zone $zone → $COLOR"
    "$OPENRGB" --noautoconnect \
        -d 0 -z "$zone" \
        -m "$MODE" --color "$COLOR" --brightness "$BRIGHTNESS" \
        || log "WARN: HyperX zone $zone failed"
done

# --- Motherboard (device 1) ---
for entry in "0:16" "1:16"; do
    zone="${entry%:*}"
    size="${entry#*:}"
    log "device 1 (Motherboard) zone $zone (size $size) → $COLOR"
    "$OPENRGB" --noautoconnect \
        -d 1 -z "$zone" -sz "$size" \
        -m "$MODE" --color "$COLOR" --brightness "$BRIGHTNESS" \
        || log "WARN: motherboard zone $zone failed"
done

for zone in 2 3 4; do
    log "device 1 (Motherboard) zone $zone → $COLOR"
    "$OPENRGB" --noautoconnect \
        -d 1 -z "$zone" \
        -m "$MODE" --color "$COLOR" --brightness "$BRIGHTNESS" \
        || log "WARN: motherboard zone $zone failed"
done

log "OK — color=$COLOR mode=$MODE aplicado a RAM y motherboard"
