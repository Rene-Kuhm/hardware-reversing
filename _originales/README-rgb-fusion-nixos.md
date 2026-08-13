> **Archived document.** This is the original README of the `Datos-RGB-Fusion-nixOS` repository,
> kept for provenance after the five hardware projects were consolidated into
> `hardware-reversing`. Links have been redirected to the corresponding directory
> in this repository. See the root [README](../README.md) for current instructions.

# RGB Fusion — NixOS/Linux LED Controller

Controls Gigabyte motherboard RGB LEDs on Linux via SMBus/I2C.

Supports **IT8295**, **IT8297**, **IT8686**, and **IT8688** ITE chips found
on Gigabyte Z790, Z690, B760, B660, Z490, Z390, and X570 boards.
Also controls AORUS external USB HID devices (coolers, chassis, keyboards).

---

## Architecture

```
rgb-fusion CLI / daemon
        │
        ├─── SMBus / I2C (/dev/i2c-*)
        │         └── IT8295 / IT8297 @ 0x58
        │               └── Motherboard ARGB headers, on-board zones
        │
        └─── USB HID (VID 0x1044)
                  └── AORUS keyboards, coolers, chassis fans
```

The IT8295/IT8297 is accessed via the Intel PCH SMBus
(`i2c-i801` kernel driver) at I2C address **0x58**.  Each zone is
configured by writing a 60-byte command block.

---

## Requirements

### Kernel modules

```bash
modprobe i2c-dev
modprobe i2c-i801
```

### User permissions

Add your user to the `i2c` group so root is not needed at runtime:

```bash
usermod -aG i2c $USER
# Log out and back in, or:
newgrp i2c
```

### Python dependencies

| Library | Purpose |
|---------|---------|
| `smbus2` | I2C/SMBus access (`/dev/i2c-*`) |
| `hid` | USB HID access (AORUS external devices) |
| `tomli` | TOML config parser (Python < 3.11 only; 3.11+ has `tomllib` built-in) |

```bash
pip install smbus2 hid tomli    # Python < 3.11
pip install smbus2 hid          # Python >= 3.11
```

---

## Installation on NixOS

### Option A — Flake (recommended)

1. Add this flake to your `flake.nix`:

```nix
{
  inputs.rgb-fusion.url = "path:/path/to/rgb-fusion-nixos";
  # or from GitHub:
  # inputs.rgb-fusion.url = "github:your-user/rgb-fusion-nixos";
}
```

2. Import the NixOS module and enable the service:

```nix
# In your nixosConfigurations.<host>.modules list:
{ inputs, ... }: {
  imports = [ inputs.rgb-fusion.nixosModules.rgbFusion ];

  services.rgbFusion = {
    enable = true;

    configText = ''
      [[zone]]
      zone       = 0
      mode       = "breath"
      color      = "FF0000"
      speed      = 5
      brightness = 9
      led_count  = 60

      [[zone]]
      zone       = 1
      mode       = "rainbow"
      color      = "FFFFFF"
      speed      = 6
      brightness = 9
    '';
  };
}
```

3. Rebuild:

```bash
nixos-rebuild switch --flake .#your-hostname
```

### Option B — Use config file on disk

```nix
services.rgbFusion = {
  enable     = true;
  configFile = /etc/rgb-fusion/config.toml;
};
```

Copy `config.example.toml` to `/etc/rgb-fusion/config.toml` and edit it.

### Option C — Run without installing (nix run)

```bash
# One-shot, apply a config
nix run .#rgb-fusion -- apply --config ./config.example.toml

# Or try a quick color
nix run .#rgb-fusion -- set --zone 0 --mode static --color 00FF00
```

### Option D — Development shell

```bash
nix develop
# now rgb_fusion.py is on PATH via the Python env
python rgb_fusion.py list
```

---

## CLI Reference

```
Usage: rgb-fusion [--debug] [--bus N] <command> [options]

Global flags:
  --debug       Enable verbose debug logging
  --bus N       Force I2C bus number (default: auto-detect)

Commands:
  list          Scan and list all detected RGB devices
  set           Configure a single LED zone
  set-all       Apply the same effect to all zones
  apply         Apply a TOML config file
  daemon        Run as a daemon, re-apply config on file changes
```

### `list`

```bash
rgb-fusion list
```

Scans all `/dev/i2c-*` buses and USB HID devices, prints a summary.

### `set`

```bash
rgb-fusion set --zone 0 --mode breath --color FF0000 --speed 5 --brightness 8

Flags:
  --zone / -z     Zone index 0-7        (default: 0)
  --mode / -m     Effect mode name      (default: static)
  --color / -c    RRGGBB hex color      (default: FF0000)
  --speed / -s    Speed 0-9             (default: 5)
  --brightness/-b Brightness 0-9        (default: 9)
  --led-count     LEDs in strip         (default: 60)
```

### `set-all`

```bash
rgb-fusion set-all --mode rainbow --speed 6 --brightness 9
rgb-fusion set-all --mode static  --color FFFFFF
rgb-fusion set-all --mode off
```

### `apply`

```bash
rgb-fusion apply --config /etc/rgb-fusion/config.toml
```

Reads the TOML file and applies every `[[zone]]` section in order.

### `daemon`

```bash
rgb-fusion daemon --config /etc/rgb-fusion/config.toml
```

Applies the config immediately, then polls for file changes every second
and re-applies.  Responds to `SIGTERM`/`SIGINT` for clean shutdown.
Intended to be managed by systemd (the NixOS module sets this up).

---

## Effect Modes

| Mode name | Description |
|-----------|-------------|
| `static` / `still` | Solid, non-animated color |
| `breath` / `breathing` | Fade in and out smoothly |
| `beat` | Pulse on a repeating beat pattern |
| `flash` | Quick on/off flash |
| `ripple` | Ripple from strip center outward |
| `random` | Randomly chosen colors |
| `colorcycle` / `cycle` | Smooth hue rotation (color ignored) |
| `wave` | Color sweep across the strip |
| `rainbow` | Full rainbow gradient animated across strip |
| `off` | All LEDs off |

`speed` (0-9): 0 = slowest, 9 = fastest.  For `breathing`, speed 5 ≈ 800 ms period.
`brightness` (0-9): 0 = LEDs off, 9 = maximum output.

---

## TOML Config Format

```toml
# One [[zone]] section per LED zone.

[[zone]]
zone       = 0          # Zone index 0-7
mode       = "breath"   # Effect mode (see table above)
color      = "FF0000"   # RRGGBB hex  (or 00RRGGBB GCC XML format)
speed      = 5          # 0-9
brightness = 9          # 0-9
led_count  = 60         # LEDs in ARGB strip (ARGB zones only)

[[zone]]
zone       = 1
mode       = "static"
color      = "00FFFF"
speed      = 5
brightness = 8
led_count  = 30
```

Copy `config.example.toml` for a complete example with all modes demonstrated.

---

## Hardware Notes

### Finding your I2C bus

```bash
# Load modules first
modprobe i2c-dev i2c-i801

# List buses — look for "SMBus I801 adapter at ..."
i2cdetect -l

# Scan that bus for the ITE chip at 0x58
i2cdetect -y <bus_number>
# Expect: address 0x58 shown as "58" (not "--")
```

### Chip identification

| Chip | Boards | Chip-ID reg 0x20 low byte |
|------|--------|--------------------------|
| IT8295 | Z690, B660, Z790, B760 | `0x95` |
| IT8297 | AORUS high-end (Z590, Z690) | `0x97` |
| IT8688 | Z390, X570, Z490 | `0x88` |
| IT8686 | Z390, H370 | `0x86` |

The `rgb-fusion list` command probes and reports the detected chip automatically.

### Board-specific zone counts

| Board family | Typical zone count |
|--------------|--------------------|
| Z790 / Z690 AORUS Master/Extreme | 6-8 |
| Z790 / Z690 AORUS Pro | 4-6 |
| B760 / B660 | 2-4 |
| Z490 / Z390 | 2-4 |

Zone indices beyond what your board supports will silently fail (the chip
ignores writes to non-existent zones).

### USB HID external devices

Known supported devices (VID 0x1044):

| PID | Device |
|-----|--------|
| 0x7A51 | AORUS WATERFORCE Cooler |
| 0x7A52 | AORUS WATERFORCE G |
| 0x7A53 | AORUS WATERFORCE EX |
| 0x7A4D | AORUS WATERFORCE X |
| 0x7A30 | AORUS C300 Glass Chassis |
| 0x7A4C | AORUS C700 Glass Chassis |
| 0x7A4A | AORUS K1 Keyboard |

USB devices are controlled automatically when detected by `set` / `set-all` /
`apply` commands if the `hid` Python library is installed.

---

## Troubleshooting

### "No /dev/i2c-* devices found"

```bash
modprobe i2c-dev i2c-i801
ls /dev/i2c-*
```

If still empty, check that BIOS has SMBus/I2C enabled (it usually is by default).

### "Permission denied on /dev/i2c-X"

```bash
# Add yourself to the i2c group
sudo usermod -aG i2c $USER
# On NixOS the udev rule from the flake handles this automatically after rebuild
```

### "No ITE RGB controller found"

- Run `i2cdetect -y <bus>` for each bus returned by `i2cdetect -l`.
- The chip should appear at address `0x58`.
- Some boards place it on bus 0 or bus 1; use `--bus N` to force.
- If address `0x5C` appears instead of `0x58`, the controller uses the alt address (detected automatically).

### LEDs don't change after running the command

1. Confirm the command exits without error (add `--debug`).
2. Check that you are writing to the correct zone (`rgb-fusion list`).
3. Some boards require a full 60-byte write via `i2c_rdwr`; this is used
   automatically when `smbus2` is >= 0.4.

### systemd service fails on boot

```bash
systemctl status rgb-fusion
journalctl -u rgb-fusion --no-pager
```

Common cause: `i2c-i801` module not yet loaded when the service starts.
The NixOS module adds `After=systemd-udev-settle.service` to handle this.
If the issue persists, add `i2c-i801` to `boot.kernelModules` explicitly
(the NixOS module already does this).

---

## Project Structure

```
rgb-fusion-nixos/
├── rgb_fusion.py               Main controller (CLI + daemon)
├── config.example.toml         Example configuration
├── flake.nix                   Nix package + NixOS module
├── README.md                   This file
└── reverse-engineering/
    ├── ANALYSIS.md             Full protocol reverse-engineering notes
    ├── ENUMS_AND_MODES.md      All LED mode enums from GCC DLLs
    └── DLL_EXPORTS.md          SMBCtrl.dll / GHidApi.dll export signatures
```

---

## License

MIT — see LICENSE file (or add one).

Reverse-engineering research derived from:
- [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) (GPL-2.0)
- Gigabyte Control Center DLL analysis
- Community SMBus traffic captures
