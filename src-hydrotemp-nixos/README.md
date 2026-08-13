# PC Monitor NixOS

A NixOS daemon that sends hardware sensor data to the USB HID display with
VID `0x3554` / PID `0xFA09` (branded "PC Monitor All" hardware).

Protocol reverse-engineered from the original .NET Windows application.

---

## Hardware

| Component | Model |
|-----------|-------|
| CPU | Intel Core i7-14700F |
| GPU | AMD Radeon RX 6600 XT |
| Display | PC Monitor USB HID (VID:3554 PID:FA09, MI_01 COL01) |

---

## Quick start

### 1. Add the flake input to your NixOS configuration

```nix
# flake.nix (your system config)
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    pc-monitor.url = "path:/path/to/pc-monitor-nixos";
    # or from a remote repo:
    # pc-monitor.url = "github:youruser/pc-monitor-nixos";
  };

  outputs = { self, nixpkgs, pc-monitor, ... }: {
    nixosConfigurations.mymachine = nixpkgs.lib.nixosSystem {
      modules = [
        pc-monitor.nixosModules.pcMonitor
        ./configuration.nix
      ];
    };
  };
}
```

### 2. Enable the service in your `configuration.nix`

```nix
services.pcMonitor = {
  enable   = true;
  logLevel = "INFO";   # DEBUG | INFO | WARNING | ERROR

  # Max values for 0-255 scaling – tune to match your hardware.
  # These match the nud_Pic* spin-box defaults in the original Windows app.
  maxCpuTemp  = 100.0;   # °C
  maxCpuPower = 253.0;   # W  (i7-14700F peak package power)
  maxCpuFreq  = 5600.0;  # MHz (max boost)
  maxGpuTemp  = 110.0;   # °C
  maxGpuPower = 160.0;   # W  (RX 6600 XT TDP)
  maxGpuFreq  = 2589.0;  # MHz
};
```

### 3. Rebuild

```bash
sudo nixos-rebuild switch
```

### 4. Check service status

```bash
systemctl status pc-monitor
journalctl -u pc-monitor -f
```

---

## Standalone / development

```bash
# Enter the dev shell (provides Python + hid library)
nix develop

# Test without connecting to the HID device
python monitor.py --dry-run --verbose

# Run directly (needs the HID device present and udev rules applied)
python monitor.py --verbose

# Build the package
nix build

# Run via nix
nix run -- --verbose
```

---

## Sensor sources

| Sensor | Linux source |
|--------|-------------|
| CPU temperature | `/sys/class/hwmon/hwmon*/` (`coretemp` driver, package temp) |
| CPU usage % | `/proc/stat` delta |
| CPU power W | `/sys/class/powercap/intel-rapl/` (RAPL energy counter delta) |
| CPU frequency | `/proc/cpuinfo` `cpu MHz` field (average across all cores) |
| CPU voltage | SuperIO hwmon (`nct6775` / `it87`) `in1` / VCore label |
| GPU temperature | `/sys/class/hwmon/hwmon*/temp1_input` (`amdgpu` driver) |
| GPU usage % | `/sys/class/drm/card*/device/gpu_busy_percent` |
| GPU power W | `/sys/class/hwmon/hwmon*/power1_average` (`amdgpu`) |
| GPU frequency | `/sys/class/hwmon/hwmon*/freq1_input` or `pp_dpm_sclk` |
| Fan RPM | `/sys/class/hwmon/hwmon*/fan1_input` |
| Water-cooling fan | `/sys/class/hwmon/hwmon*/fan2_input` (SuperIO fan2) |

NVIDIA GPUs are supported via `nvidia-smi` as a fallback.

---

## Kernel modules

The following kernel modules must be loaded for full sensor coverage:

```nix
# configuration.nix
boot.kernelModules = [
  "coretemp"   # Intel CPU temperature
  "nct6775"    # SuperIO (fans, voltages) – check dmesg for your chip name
  # "it87"     # Alternative SuperIO driver
];
```

To discover which hwmon driver your board uses:

```bash
sensors-detect   # from lm_sensors (included in the dev shell / system packages)
sensors
```

---

## udev rules

The flake automatically installs udev rules giving the `pc-monitor` group
read/write access to the HID device without requiring root:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="fa09",
    MODE="0660", GROUP="pc-monitor"
```

After a cold plug, trigger udev manually if needed:

```bash
sudo udevadm trigger --subsystem-match=hidraw
```

---

## HID report layout (for reference)

```
Byte  0   : 0x00  report ID
Byte  1   : 0x01  header
Byte  2   : 0x02  header
Byte  3   : CPU temperature  (scaled 0-255)
Byte  4   : CPU usage %      (scaled 0-255)
Byte  5   : CPU power W      (scaled 0-255)
Byte  6   : CPU freq MHz     (scaled 0-255)
Byte  7   : CPU voltage V    (scaled 0-255)
Byte  8   : GPU temperature  (scaled 0-255)
Byte  9   : GPU usage %      (scaled 0-255)
Byte 10   : GPU power W      (scaled 0-255)
Byte 11   : GPU freq MHz     (scaled 0-255)
Byte 12   : Water-cool fan   (scaled 0-255)
Byte 13   : System fan RPM   (scaled 0-255)
Byte 14-35: reserved (0x00)
Byte 36-63: padding  (0x00)
```

Scale formula: `send_value = int(actual / max * 255)`

Update rate: 200 ms (matches `Thread.Sleep(0xC8)` in original firmware).

---

## Troubleshooting

**Device not found**
- Check `lsusb | grep 3554` – confirm the device is enumerated.
- Verify udev rules are applied: `ls -l /dev/hidraw*`
- Trigger rules: `sudo udevadm trigger && sudo udevadm settle`

**No sensor data / all zeros**
- Run `sensors` to verify lm_sensors can see the hardware.
- Check that `coretemp` and `nct6775` (or your board's SuperIO driver) are loaded.
- For RAPL, confirm `/sys/class/powercap/intel-rapl/` exists.

**GPU sensors missing (AMD)**
- Ensure the `amdgpu` driver is active: `lsmod | grep amdgpu`
- Check `ls /sys/class/hwmon/` for a hwmon with `name == amdgpu`.
- For `gpu_busy_percent`: `cat /sys/class/drm/card0/device/gpu_busy_percent`

**Permission errors on RAPL**
- The service runs with `CAP_DAC_READ_SEARCH` to bypass read restrictions.
- If still failing, add `acl` udev rules or run `sensors-detect` as root once.
