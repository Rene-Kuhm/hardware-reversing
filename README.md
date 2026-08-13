# hardware-reversing

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20NixOS-1793D1)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python)
![Protocol](https://img.shields.io/badge/protocol-USB%20HID-orange)
![License](https://img.shields.io/badge/license-MIT-green)

Userspace drivers for PC hardware with no official Linux or macOS support: AIO cooler displays, motherboard RGB lighting, and USB lighting controllers.

Every driver here was built the same way — capture the USB/HID traffic of the proprietary Windows software, decode the protocol, and reimplement it from scratch in Python. The protocol analysis is documented in full, so the findings are useful even if you never run this code.

## Devices

| Device | What it is | Protocol | Linux | macOS | NixOS |
|---|---|---|---|---|---|
| **HydroTemp AIO display** | Case display for CPU/GPU temps, fan and pump RPM | USB HID, VID `0x5131` PID `0x2007` (FBB), 65-byte reports @ 200 ms | ✅ production | ✅ | ✅ |
| **RGB Fusion** | Gigabyte motherboard lighting (ITE8297) | Vendor HID, reversed from the official DLL | ✅ | ✅ | ✅ |
| **Stream Station** | USB lighting controller | Raw USB, proprietary protocol | — | — | ✅ |

Reference software analysed: `PC Monitor All.exe` (.NET 4.x / CyUSB) on Windows 11 Pro.

## Protocol findings

The three findings that cost the most time, in case they save yours:

- **The display is not the device you first enumerate.** It exposes `VID 0x5131 / PID 0x2007`, easily confused with the CX wireless receiver on the same bus. You must select the vendor HID interface by `usage_page = 0xFF02`; matching the first HID interface lands you on the keyboard and every write returns `EPIPE`.
- **Writes need a 65-byte buffer** — 64 bytes of payload plus the 1-byte `hidapi` report-ID prefix — to match the raw CyUSB transfer the Windows driver performs.
- **`buf[9]` is the CPU temperature**, not the per-thread maximum as the packet layout suggests. Related: `buf[6]` (GPU power) must be `0` or the display refuses to render the real CPU temperature.

Full analysis:

| Document | Contents |
|---|---|
| [`docs/hydrotemp-aio/AIO-Display-Protocol-Analysis.md`](docs/hydrotemp-aio/AIO-Display-Protocol-Analysis.md) | Complete display protocol (24 KB) |
| [`docs/hydrotemp-aio/PROTOCOL_ANALYSIS.md`](docs/hydrotemp-aio/PROTOCOL_ANALYSIS.md) | HID report structure |
| [`docs/hydrotemp-aio/IL_SENDDATA2_DECODED.md`](docs/hydrotemp-aio/IL_SENDDATA2_DECODED.md) | `IL_SENDDATA2` decoding |
| [`docs/rgb-fusion/ANALYSIS.md`](docs/rgb-fusion/ANALYSIS.md) | RGB Fusion analysis |
| [`docs/rgb-fusion/DLL_EXPORTS.md`](docs/rgb-fusion/DLL_EXPORTS.md) | Proprietary DLL exports |
| [`docs/rgb-fusion/ENUMS_AND_MODES.md`](docs/rgb-fusion/ENUMS_AND_MODES.md) | Effect modes and enumerations |
| [`docs/stream-station/USB_PROTOCOL.md`](docs/stream-station/USB_PROTOCOL.md) | Stream Station USB protocol |

## Requirements

- Python 3.10+
- `hidapi`
- `openrgb` (only for RGB keepalive on Linux)

## Installation — Linux (Arch / CachyOS)

```bash
sudo pacman -S hidapi openrgb
```

Copy the launcher scripts and enable the user services:

```bash
cp hydrotemp-aio/linux/bin/*.sh ~/bin/
chmod +x ~/bin/hydrotemp-start.sh ~/bin/rgb-keepalive.sh

mkdir -p ~/.config/systemd/user/
cp hydrotemp-aio/linux/systemd/*.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now hydrotemp.service
systemctl --user enable --now rgb-init.service
```

## Installation — macOS

Builds a signed `.pkg` / `.dmg` and installs a LaunchAgent that starts the driver at login:

```bash
cd hydrotemp-aio/macos/build
./build.sh
```

Tested on Intel Mac (Xeon W / Mac Pro) and Hackintosh.

## Installation — NixOS

Each device ships its own flake:

```bash
nix run ./hydrotemp-aio/nixos
nix run ./rgb-fusion/nixos
nix run ./stream-station/nixos
```

## Usage

```bash
python3 hydrotemp-aio/monitor.py --verbose            # run with sensor logging
python3 hydrotemp-aio/monitor.py --dry-run --verbose  # no HID device required
```

Sensors read from `sysfs`:

| Metric | Source |
|---|---|
| CPU package temperature | `coretemp` |
| CPU usage | `/proc/stat` |
| GPU temperature and usage | `amdgpu` (NVIDIA supported in the NixOS variant) |
| Fan RPM | `hwmon/*/fan*_input` |
| Pump RPM | `nct6775` / `nct6798` / `it87` |

### RGB keepalive

Gigabyte boards reset their lighting to default periodically. The keepalive re-applies the OpenRGB profile on an interval, configurable by environment variable:

| Variable | Default | Description |
|---|---|---|
| `RGB_DEVICE_ID` | `1` | OpenRGB motherboard device index |
| `RGB_MEMORY_DEVICE_ID` | `0` | OpenRGB memory device index |
| `RGB_MODE` | `static` | RGB mode (static, direct, …) |
| `RGB_COLOR` | `FFFFFF` | Hex colour value |
| `RGB_BRIGHTNESS` | `100` | Brightness percentage |
| `RGB_ARG_SIZE` | `30` | ARGB zone LED count (D_LED1 / D_LED2) |
| `RGB_INTERVAL_SEC` | `20` | Re-apply interval in seconds |

## Hardware tested

| Component | Device |
|---|---|
| AIO display | HydroTemp / PC Monitor All case display — VID `5131` PID `2007` (FBB) |
| Motherboard RGB | Gigabyte Z790 AORUS (ITE8297) |
| Systems | Arch Linux / CachyOS, NixOS, macOS (Intel) |

## Repository layout

```
docs/                     Protocol analysis, per device
hydrotemp-aio/
  monitor.py              canonical implementation (Linux, in production)
  linux/                  systemd units and launcher scripts
  macos/                  monitor_macos.py, LaunchAgent, PKG/DMG installers
  nixos/                  flake.nix and NixOS variant
rgb-fusion/               rgb_fusion.py, ITE8297 controller, flake
stream-station/           stream_station.py, flake
_originales/              READMEs of the five original repositories
```

### Which implementation to use

`hydrotemp-aio/monitor.py` is canonical — it is the version running in production on CachyOS and the most recent (May 2026). Compared to the NixOS variant it scans `fan*_input` instead of only `fan1_input`, and distinguishes "fan present but stopped" (0 RPM) from "no fan found".

`hydrotemp-aio/macos/monitor_macos.py` is a separate implementation, not a copy: macOS reads sensors through different system APIs.

## Provenance

This repository consolidates five earlier repos **with their full history preserved** (41 commits). The reverse-engineering process lives in the commit messages and is part of the value.

| Original repository | Contribution |
|---|---|
| `hydrotemp-rgb-arch` | Canonical Linux implementation (May 2026) |
| `Datos-xyz-hydrotemp` | Real display protocol, reversing docs |
| `hydrotemp-aio-mac` | macOS port, installers, ITE8297 controller |
| `Datos-RGB-Fusion-nixOS` | RGB Fusion reversing + NixOS module |
| `Datos-Stream-Station-nixos` | Stream Station reversing + NixOS module |

## License

MIT — see [LICENSE](LICENSE).
