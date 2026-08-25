#!/usr/bin/env bash
# Configuración profesional de la webcam Logitech MX Brio.
# Aplica valores balanceados para uso de oficina / streaming / videollamadas.
# Se puede ajustar individualmente con `v4l2-ctl -d /dev/video0 -c <ctrl>=<valor>`.
set -uo pipefail

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

# Buscar el primer dispositivo de video Logitech MX Brio (046d:0944).
VIDEO_DEV="$(v4l2-ctl --list-devices 2>/dev/null \
    | awk '/MX Brio/{p=1; print; next} p && /\/{2}/{p=0; next} p && /dev\/video/{print; exit}' \
    | grep -oE '/dev/video[0-9]+' \
    | head -1)"

if [ -z "${VIDEO_DEV:-}" ]; then
    log "MX Brio no detectada — saliendo sin error para no romper boot"
    exit 0
fi

log "Configurando MX Brio en $VIDEO_DEV"

V4L2="v4l2-ctl -d $VIDEO_DEV"

# Resolución / codec: 1080p@30 MJPEG (lo que usan Teams/Zoom internamente).
# Para 4K@30 cambiá a: pixelformat=MJPG width=3840 height=2160
$V4L2 --set-fmt-video=width=1920,height=1080,pixelformat=MJPG
log "  fmt: 1920x1080 MJPEG"

# Imagen balanceada para oficina (luz artificial ~4000K).
$V4L2 -c brightness=128       # 0-255, default neutro
$V4L2 -c contrast=140         # sube contraste para nitidez
$V4L2 -c saturation=160       # colores vibrantes
$V4L2 -c sharpness=200        # bordes nítidos

# Balance de blancos automático (luz cambiante en oficina).
$V4L2 -c white_balance_automatic=1

# Exposición automática en modo Aperture Priority (default = 3).
$V4L2 -c auto_exposure=3

# Dynamic framerate (1 = habilitado, suaviza cambios de luz).
$V4L2 -c exposure_dynamic_framerate=1

# Power line frequency: Argentina/Uruguay/España = 50Hz.
# Si ves parpadeo/flicker en la imagen, cambiá este valor.
# 0 = Disabled, 1 = 50Hz, 2 = 60Hz
$V4L2 -c power_line_frequency=1
log "  power_line: 50Hz"

# Backlight compensation desactivado (oficina iluminada).
$V4L2 -c backlight_compensation=0

# Autofocus continuo (la MX Brio tiene PDAF excelente).
$V4L2 -c focus_automatic_continuous=1

# Zoom absoluto al 100% (1x) por defecto — sin distorsión digital.
$V4L2 -c zoom_absolute=100

log "MX Brio lista: 1080p30 MJPEG, autofocus, WB auto, 50Hz"
log "Para ajustar: v4l2-ctl -d $VIDEO_DEV -L (lista controles)"
