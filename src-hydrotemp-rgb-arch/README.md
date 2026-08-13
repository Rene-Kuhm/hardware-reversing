# HydroTemp RGB Arch

![Platform](https://img.shields.io/badge/platform-Arch%20Linux%20%7C%20CachyOS-1793D1?logo=arch-linux)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

Daemon for the HydroTemp AIO liquid cooler display and RGB Fusion keepalive for Arch Linux / CachyOS. Adapted from [Datos-xyz-hydrotemp](https://github.com/Rene-Kuhm/Datos-xyz-hydrotemp) and [Datos-RGB-Fusion-nixOS](https://github.com/Rene-Kuhm/Datos-RGB-Fusion-nixOS).

## Overview

This project provides two core services for Arch Linux systems with Gigabyte AIO coolers and motherboards:

| Service | Description |
|---------|-------------|
| **HydroTemp Monitor** | Reads hardware sensors from `sysfs`/`hwmon` and sends 65-byte HID reports every 200ms to the AIO display (VID `5131` PID `2007`) |
| **RGB Keepalive** | Periodically re-applies the OpenRGB profile to prevent the motherboard from resetting colors to default |

## Requirements

- Arch Linux / CachyOS
- Python 3.10+
- `hidapi` — `pacman -S hidapi`
- `openrgb` — `pacman -S openrgb`

## Repository Structure

```
.
├── monitor.py               HID display daemon (CPU temp, GPU temp, fan/pump RPM)
├── bin/
│   ├── hydrotemp-start.sh   Monitor launcher script
│   └── rgb-keepalive.sh     OpenRGB profile keepalive
├── systemd/
│   ├── hydrotemp.service    User service for the monitor daemon
│   └── rgb-init.service     User service for RGB keepalive
└── README.md
```

## Usage

### HydroTemp Monitor

```bash
python3 monitor.py --verbose          # Run with sensor logging
python3 monitor.py --dry-run --verbose # Dry-run without HID device
```

The daemon reads the following sensors from `sysfs`:

- CPU package temperature (`coretemp`)
- CPU usage (`/proc/stat`)
- GPU temperature and usage (`amdgpu`)
- Fan RPM (`hwmon/*/fan*_input`)
- Pump RPM (`nct6775`/`nct6798`/`it87`)

### RGB Keepalive

The keepalive script accepts environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `RGB_DEVICE_ID` | `1` | OpenRGB motherboard device index |
| `RGB_MEMORY_DEVICE_ID` | `0` | OpenRGB memory device index |
| `RGB_MODE` | `static` | RGB mode (static, direct, etc.) |
| `RGB_COLOR` | `FFFFFF` | Hex color value |
| `RGB_BRIGHTNESS` | `100` | Brightness percentage |
| `RGB_ARG_SIZE` | `30` | ARGB zone LED count (D_LED1/D_LED2) |
| `RGB_INTERVAL_SEC` | `20` | Re-apply interval in seconds |

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Rene-Kuhm/hydrotemp-rgb-arch.git
```

2. Install dependencies:

```bash
sudo pacman -S hidapi openrgb
```

3. Copy launch scripts to `~/bin/`:

```bash
cp bin/hydrotemp-start.sh ~/bin/
cp bin/rgb-keepalive.sh ~/bin/
chmod +x ~/bin/hydrotemp-start.sh ~/bin/rgb-keepalive.sh
```

4. Install systemd user services:

```bash
mkdir -p ~/.config/systemd/user/
cp systemd/hydrotemp.service ~/.config/systemd/user/
cp systemd/rgb-init.service ~/.config/systemd/user/
```

5. Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now hydrotemp.service
systemctl --user enable --now rgb-init.service
```

## Hardware Compatibility

| Component | Device | Protocol |
|-----------|--------|----------|
| AIO Display | VID `5131` PID `2007` (FBB) | USB HID, 65-byte reports @ 200ms |
| Motherboard RGB | Gigabyte Z790 AORUS | OpenRGB CLI |

## Related Projects

- [Datos-xyz-hydrotemp](https://github.com/Rene-Kuhm/Datos-xyz-hydrotemp) — NixOS version with NVIDIA support and full protocol analysis
- [Datos-RGB-Fusion-nixOS](https://github.com/Rene-Kuhm/Datos-RGB-Fusion-nixOS) — NixOS RGB Fusion module with reverse engineering docs

## License

MIT