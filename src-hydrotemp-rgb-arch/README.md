# hydrotemp-rgb-arch

HydroTemp AIO monitor + RGB Fusion keepalive + LEDBLE RGB control for Arch Linux / CachyOS.

Adaptado de [Datos-xyz-hydrotemp](https://github.com/Rene-Kuhm/Datos-xyz-hydrotemp) y [Datos-RGB-Fusion-nixOS](https://github.com/Rene-Kuhm/Datos-RGB-Fusion-nixOS) para Arch Linux.

## Components

### monitor.py — HydroTemp HID Display Daemon

Sends hardware sensor data (CPU temp, GPU temp, fan RPM, etc.) to the USB HID display (VID:5131 PID:2007) on AIO liquid coolers.

Dependencies:
- `python-hid` (Arch: `pacman -S hidapi`)
- Python 3.10+

```bash
# Run directly
python3 monitor.py --verbose

# Dry-run (no HID device needed)
python3 monitor.py --dry-run --verbose
```

### led_control.py — LEDBLE BLE RGB Controller

Controls an LEDBLE RGB LED strip via Bluetooth Low Energy.

Dependencies:
- `python-bleak` (Arch: `pacman -S python-bleak`)

```bash
# Turn on (default: white)
python3 led_control.py on

# Turn on with color
python3 led_control.py on red
python3 led_control.py on 255 128 0

# Turn off
python3 led_control.py off

# Toggle
python3 led_control.py toggle

# Status
python3 led_control.py status
```

Set your device MAC via environment:
```bash
export LEDBLE_MAC="FF:FF:38:61:AB:31"
```

### bin/rgb-keepalive.sh — OpenRGB Keepalive

Periodically re-applies the RGB profile using OpenRGB to prevent motherboard from resetting colors.

Dependencies:
- `openrgb` (Arch: `pacman -S openrgb`)

Environment variables (with defaults):
- `RGB_DEVICE_ID=1`
- `RGB_MEMORY_DEVICE_ID=0`
- `RGB_MODE=static`
- `RGB_COLOR=FFFFFF`
- `RGB_BRIGHTNESS=100`
- `RGB_ARG_SIZE=30`
- `RGB_INTERVAL_SEC=20`

### bin/hydrotemp-start.sh — Monitor launcher

Script that launches `monitor.py`. Used by the systemd service.

### waybar/waybar_led.sh — Waybar LED Module

Waybar custom module that shows LED on/off state and allows toggle/color change via click.

Dependencies:
- `led_control.py`
- `wofi` or `rofi` (for color menu on right-click)

Waybar config:
```json
"custom/led": {
    "exec": "/path/to/hydrotemp-rgb-arch/waybar/waybar_led.sh status",
    "on-click": "/path/to/hydrotemp-rgb-arch/waybar/waybar_led.sh left-click",
    "on-click-right": "/path/to/hydrotemp-rgb-arch/waybar/waybar_led.sh right-click",
    "on-click-middle": "/path/to/hydrotemp-rgb-arch/waybar/waybar_led.sh middle-click",
    "interval": 5,
    "return-type": "json"
}
```

## Installation

1. Clone the repo:
```bash
git clone https://github.com/Rene-Kuhm/hydrotemp-rgb-arch.git ~/hydrotemp-rgb-arch
```

2. Install dependencies:
```bash
sudo pacman -S hidapi python-bleak openrgb
```

3. Copy launch scripts to `~/bin/`:
```bash
cp bin/hydrotemp-start.sh ~/bin/
cp bin/rgb-keepalive.sh ~/bin/
chmod +x ~/bin/hydrotemp-start.sh ~/bin/rgb-keepalive.sh
```

4. Edit `~/bin/hydrotemp-start.sh` to point to your clone path if different.

5. Copy systemd user services:
```bash
mkdir -p ~/.config/systemd/user/
cp systemd/hydrotemp.service ~/.config/systemd/user/
cp systemd/rgb-init.service ~/.config/systemd/user/
```

6. Enable and start services:
```bash
systemctl --user daemon-reload
systemctl --user enable --now hydrotemp.service
systemctl --user enable --now rgb-init.service
```

## Hardware

- **HydroTemp display**: VID `5131` PID `2007` (FBB display)
- **Motherboard RGB**: Gigabyte Z790 AORUS (via OpenRGB)
- **LEDBLE RGB strip**: BLE device (configurable MAC via `LEDBLE_MAC`)