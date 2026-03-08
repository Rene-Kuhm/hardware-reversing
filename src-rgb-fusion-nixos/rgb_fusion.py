#!/usr/bin/env python3
"""
rgb_fusion.py — RGB Fusion LED Controller for NixOS/Linux
==========================================================
Controls Gigabyte motherboard RGB LEDs via SMBus/I2C (IT8295/IT8297 chips)
and USB HID external devices (Gigabyte AORUS, VID 0x1044).

Supported chips  : IT8295, IT8297, IT8686, IT8688
I2C address      : 0x58 (SMBus PCH bus)
Kernel modules   : i2c-dev, i2c-i801
Python deps      : smbus2, hid, tomli (or Python 3.11+ tomllib)

Usage
-----
    rgb-fusion list
    rgb-fusion set   --zone 0 --mode breath --color FF0000 --speed 5 --brightness 8
    rgb-fusion set-all --mode static --color 00FF00
    rgb-fusion apply --config /etc/rgb-fusion/config.toml
    rgb-fusion daemon [--config /etc/rgb-fusion/config.toml]
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional imports — graceful degradation when libraries are absent
# ---------------------------------------------------------------------------
try:
    import smbus2
    _SMBUS2_AVAILABLE = True
except ImportError:
    _SMBUS2_AVAILABLE = False

try:
    import hid as _hid_module
    _HID_AVAILABLE = True
except ImportError:
    _HID_AVAILABLE = False

try:
    import tomllib                       # Python 3.11+
    _TOMLLIB_AVAILABLE = True
except ImportError:
    try:
        import tomli as tomllib          # type: ignore[no-redef]
        _TOMLLIB_AVAILABLE = True
    except ImportError:
        tomllib = None                   # type: ignore[assignment]
        _TOMLLIB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("rgb_fusion")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ITE chip I2C addresses (7-bit)
I2C_ADDR_PRIMARY = 0x58
I2C_ADDR_ALT     = 0x5C

# USB VID for all Gigabyte AORUS external RGB devices
USB_VID_GIGABYTE = 0x1044

# Chip names
CHIP_UNKNOWN = "unknown"
CHIP_IT8295  = "IT8295"
CHIP_IT8297  = "IT8297"
CHIP_IT8686  = "IT8686"
CHIP_IT8688  = "IT8688"

# Register used to probe chip identity (low byte of chip ID)
CHIP_PROBE_REG = 0x20
CHIP_ID_LOW_BYTE: dict[int, str] = {
    0x95: CHIP_IT8295,
    0x97: CHIP_IT8297,
    0x86: CHIP_IT8686,
    0x88: CHIP_IT8688,
}

# ---------------------------------------------------------------------------
# IT8295 / IT8297 effect mode codes (60-byte block protocol)
# These align with the OpenRGB IT8295 implementation and observed GCC traffic.
# ---------------------------------------------------------------------------
EFFECT_OFF        = 0x00
EFFECT_STATIC     = 0x01
EFFECT_BREATHING  = 0x02
EFFECT_BEAT       = 0x03
EFFECT_FLASH      = 0x04
EFFECT_RIPPLE     = 0x06
EFFECT_RANDOM     = 0x07
EFFECT_COLORCYCLE = 0x0A
EFFECT_WAVE       = 0x0B
EFFECT_RAINBOW    = 0x0C

# Human-readable name → effect code
MODE_NAME_TO_CODE: dict[str, int] = {
    "off":        EFFECT_OFF,
    "static":     EFFECT_STATIC,
    "still":      EFFECT_STATIC,
    "breath":     EFFECT_BREATHING,
    "breathing":  EFFECT_BREATHING,
    "beat":       EFFECT_BEAT,
    "flash":      EFFECT_FLASH,
    "ripple":     EFFECT_RIPPLE,
    "random":     EFFECT_RANDOM,
    "colorcycle": EFFECT_COLORCYCLE,
    "cycle":      EFFECT_COLORCYCLE,
    "wave":       EFFECT_WAVE,
    "rainbow":    EFFECT_RAINBOW,
}

# Speed index 0-9 → raw timing byte written to hardware
# Higher index = faster animation (shorter period)
SPEED_TABLE: list[int] = [
    0xFF,  # 0 — slowest (~1600 ms period for breathing)
    0xD0,
    0xA0,
    0x80,
    0x60,
    0x40,  # 5 — mid
    0x30,
    0x20,
    0x10,
    0x08,  # 9 — fastest (~400 ms period for breathing)
]

# Brightness index 0-9 → raw brightness byte
BRIGHTNESS_TABLE: list[int] = [
    0x00,  # 0 — off
    0x1C,
    0x38,
    0x55,
    0x71,
    0x8E,  # 5 — mid
    0xAA,
    0xC6,
    0xE3,
    0xFF,  # 9 — full
]

# Block size required by IT8295
IT8295_BLOCK_SIZE = 60

# Register offset for the 60-byte color/mode block
IT8295_REG_BLOCK = 0x00

# Zone-select register prefix byte used by some firmware
IT8295_REG_ZONE_SEL = 0x58

# Maximum zones the protocol supports
MAX_ZONES = 8

# Fallback LED count for ARGB zones when not specified
DEFAULT_LED_COUNT = 60

# Default config file path (used by NixOS service and daemon mode)
DEFAULT_CONFIG_PATH = Path("/etc/rgb-fusion/config.toml")

# Known Gigabyte AORUS USB HID product IDs (from Device.ini)
AORUS_PRODUCTS: dict[int, str] = {
    0x7A34: "AORUS H5 Header",
    0x7A30: "AORUS C300 Glass Chassis",
    0x7A4C: "AORUS C700 Glass Chassis",
    0x7A50: "AORUS P1200W PSU",
    0x7A51: "AORUS WATERFORCE Cooler",
    0x7A52: "AORUS WATERFORCE G Cooler",
    0x7A53: "AORUS WATERFORCE EX Cooler",
    0x7A4D: "AORUS WATERFORCE X Cooler",
    0x7A4A: "AORUS K1 Keyboard",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ZoneConfig:
    """Configuration for a single RGB/ARGB LED zone."""

    zone:       int = 0
    mode:       str = "static"
    r:          int = 255
    g:          int = 0
    b:          int = 0
    speed:      int = 5       # 0-9
    brightness: int = 9       # 0-9
    led_count:  int = DEFAULT_LED_COUNT

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict, zone_index: int = 0) -> "ZoneConfig":
        """Parse a zone config dict (as loaded from TOML [[zone]] section)."""
        color_str = str(d.get("color", "FF0000")).strip().lstrip("#")
        # Accept both RRGGBB (6) and 00RRGGBB (8, GCC XML format)
        if len(color_str) == 8:
            color_str = color_str[2:]
        if len(color_str) != 6:
            raise ValueError(
                f"Invalid color '{color_str}' in zone {zone_index}; "
                "expected RRGGBB or 00RRGGBB hex."
            )
        r = int(color_str[0:2], 16)
        g = int(color_str[2:4], 16)
        b = int(color_str[4:6], 16)
        return cls(
            zone       = int(d.get("zone", zone_index)),
            mode       = str(d.get("mode", "static")).lower(),
            r=r, g=g, b=b,
            speed      = int(d.get("speed", 5)),
            brightness = int(d.get("brightness", 9)),
            led_count  = int(d.get("led_count", DEFAULT_LED_COUNT)),
        )

    def color_hex(self) -> str:
        """Return color as uppercase RRGGBB hex string."""
        return f"{self.r:02X}{self.g:02X}{self.b:02X}"

    def __str__(self) -> str:
        return (
            f"Zone {self.zone}: mode={self.mode} color=#{self.color_hex()} "
            f"speed={self.speed} brightness={self.brightness} leds={self.led_count}"
        )


@dataclass
class FusionConfig:
    """Top-level configuration containing all zone configs."""

    zones: List[ZoneConfig] = field(default_factory=list)

    # ------------------------------------------------------------------
    @classmethod
    def from_toml(cls, path: Path) -> "FusionConfig":
        if tomllib is None:
            raise RuntimeError(
                "No TOML library available. "
                "Install tomli (pip install tomli) or use Python 3.11+."
            )
        with open(path, "rb") as fh:
            data = tomllib.load(fh)

        zones: List[ZoneConfig] = []
        for i, zone_dict in enumerate(data.get("zone", [])):
            zones.append(ZoneConfig.from_dict(zone_dict, i))

        if not zones:
            log.warning("Config file %s contains no [[zone]] sections.", path)
        return cls(zones=zones)

    @classmethod
    def from_cli(
        cls,
        zone: int,
        mode: str,
        color: str,
        speed: int,
        brightness: int,
        led_count: int = DEFAULT_LED_COUNT,
    ) -> "FusionConfig":
        d = {
            "zone": zone, "mode": mode, "color": color,
            "speed": speed, "brightness": brightness, "led_count": led_count,
        }
        return cls(zones=[ZoneConfig.from_dict(d, zone)])

    @classmethod
    def all_zones(
        cls,
        mode: str,
        color: str,
        speed: int,
        brightness: int,
    ) -> "FusionConfig":
        zones = []
        for i in range(MAX_ZONES):
            d = {"zone": i, "mode": mode, "color": color,
                 "speed": speed, "brightness": brightness}
            zones.append(ZoneConfig.from_dict(d, i))
        return cls(zones=zones)


# ---------------------------------------------------------------------------
# IT8295 / IT8297 I2C protocol helpers
# ---------------------------------------------------------------------------

def build_it8295_block(cfg: ZoneConfig) -> bytes:
    """
    Build the 60-byte command block for the IT8295/IT8297 chip.

    Layout (derived from OpenRGB IT8295 driver + GCC SMBus traffic):
        [0]     Effect mode byte (EFFECT_* constant)
        [1]     Red channel   (0-255)
        [2]     Green channel (0-255)
        [3]     Blue channel  (0-255)
        [4]     Speed byte    (from SPEED_TABLE, index 0-9)
        [5]     Brightness    (from BRIGHTNESS_TABLE, index 0-9)
        [6]     LED count     (number of LEDs in the ARGB strip)
        [7-59]  Reserved / padding zeros
    """
    mode_code = MODE_NAME_TO_CODE.get(cfg.mode.lower(), EFFECT_STATIC)
    speed_val = SPEED_TABLE[max(0, min(9, cfg.speed))]
    bri_val   = BRIGHTNESS_TABLE[max(0, min(9, cfg.brightness))]

    block = bytearray(IT8295_BLOCK_SIZE)
    block[0] = mode_code
    block[1] = cfg.r & 0xFF
    block[2] = cfg.g & 0xFF
    block[3] = cfg.b & 0xFF
    block[4] = speed_val
    block[5] = bri_val
    block[6] = cfg.led_count & 0xFF
    return bytes(block)


# ---------------------------------------------------------------------------
# I2C bus detection
# ---------------------------------------------------------------------------

def _probe_i2c_addr(bus_num: int, addr: int) -> Optional[str]:
    """
    Probe one I2C bus + address combination.
    Returns chip name string, or None if nothing responds.
    """
    try:
        with smbus2.SMBus(bus_num) as bus:
            # Primary probe: chip-ID register 0x20
            for reg in (0x20, 0x00):
                try:
                    val = bus.read_byte_data(addr, reg)
                    chip = CHIP_ID_LOW_BYTE.get(val & 0xFF)
                    if chip:
                        return chip
                    # Something responded even if we don't know the chip
                    if reg == 0x20:
                        continue
                    return CHIP_UNKNOWN
                except OSError:
                    continue
    except (OSError, PermissionError):
        pass
    return None


def find_rgb_i2c_buses() -> List[Tuple[int, int, str]]:
    """
    Scan all /dev/i2c-* buses for ITE RGB controller chips.

    Returns a list of (bus_number, i2c_address, chip_name) tuples.
    """
    if not _SMBUS2_AVAILABLE:
        log.error("smbus2 is not installed — cannot scan I2C buses.")
        return []

    results: List[Tuple[int, int, str]] = []
    i2c_devs = sorted(Path("/dev").glob("i2c-*"))

    if not i2c_devs:
        log.warning(
            "No /dev/i2c-* devices found. "
            "Ensure kernel modules i2c-dev and i2c-i801 are loaded "
            "('modprobe i2c-dev i2c-i801') and you are in the 'i2c' group."
        )
        return results

    log.debug("Scanning %d I2C buses...", len(i2c_devs))
    for dev in i2c_devs:
        try:
            bus_num = int(dev.name.split("-")[1])
        except (IndexError, ValueError):
            continue

        for addr in (I2C_ADDR_PRIMARY, I2C_ADDR_ALT):
            chip = _probe_i2c_addr(bus_num, addr)
            if chip is not None:
                log.info(
                    "Found %s on /dev/i2c-%d at address 0x%02X",
                    chip, bus_num, addr,
                )
                results.append((bus_num, addr, chip))
                break   # don't check ALT address if primary matched

    return results


# ---------------------------------------------------------------------------
# IT8295 / IT8297 controller class
# ---------------------------------------------------------------------------

class IT8295Controller:
    """
    Low-level driver for ITE IT8295 / IT8297 chips over Linux I2C/SMBus.

    The chip is controlled by writing a 60-byte block to register 0x00
    of I2C address 0x58 on the PCH SMBus.  Each zone requires a zone-select
    prefix write before the block write (firmware-dependent).

    Use as a context manager:
        with IT8295Controller(bus_num=3) as ctrl:
            ctrl.set_zone(zone_cfg)
    """

    def __init__(self, bus_num: int, addr: int = I2C_ADDR_PRIMARY):
        if not _SMBUS2_AVAILABLE:
            raise RuntimeError(
                "smbus2 library not available. "
                "Install it: pip install smbus2  or  nix-shell -p python3Packages.smbus2"
            )
        self.bus_num = bus_num
        self.addr    = addr
        self._bus: Optional["smbus2.SMBus"] = None

    # ------------------------------------------------------------------
    def open(self) -> None:
        self._bus = smbus2.SMBus(self.bus_num)
        log.debug("Opened /dev/i2c-%d", self.bus_num)

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None
            log.debug("Closed /dev/i2c-%d", self.bus_num)

    def __enter__(self) -> "IT8295Controller":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    def _write_block(self, reg: int, data: bytes) -> None:
        """
        Write an arbitrary-length block to a register.

        smbus2.write_i2c_block_data is capped at 32 bytes by the SMBus spec.
        For longer payloads (the IT8295 needs 60 bytes) we fall back to a
        raw i2c_rdwr message which bypasses the 32-byte limit.
        """
        assert self._bus is not None

        if len(data) <= 32:
            self._bus.write_i2c_block_data(self.addr, reg, list(data))
        else:
            # Build raw I2C write: [register_byte] + [data...]
            msg = smbus2.i2c_msg.write(self.addr, [reg] + list(data))
            self._bus.i2c_rdwr(msg)

    def _write_zone_select(self, zone: int) -> None:
        """
        Send the optional zone-select command that some IT8295 firmware
        variants require before accepting the 60-byte effect block.
        Silently ignored if the hardware does not support it.
        """
        assert self._bus is not None
        try:
            self._bus.write_i2c_block_data(
                self.addr, IT8295_REG_ZONE_SEL, [zone & 0xFF]
            )
            time.sleep(0.001)   # 1 ms settle
        except OSError as exc:
            log.debug("Zone-select write not required (ignored: %s)", exc)

    # ------------------------------------------------------------------
    def set_zone(self, cfg: ZoneConfig) -> None:
        """Apply a ZoneConfig to the chip."""
        assert self._bus is not None

        # 1. Optional zone select
        self._write_zone_select(cfg.zone)

        # 2. Write the 60-byte effect block
        block = build_it8295_block(cfg)
        self._write_block(IT8295_REG_BLOCK, block)
        time.sleep(0.005)   # 5 ms — give MCU time to process

        log.info(str(cfg))

    def set_zones(self, configs: List[ZoneConfig]) -> None:
        """Apply a list of ZoneConfig objects in order."""
        for cfg in configs:
            self.set_zone(cfg)

    def reset_all(self) -> None:
        """Turn off all zones (send OFF effect to every zone 0-7)."""
        log.info("Resetting all zones to OFF...")
        for i in range(MAX_ZONES):
            off_cfg = ZoneConfig(zone=i, mode="off", r=0, g=0, b=0)
            try:
                self.set_zone(off_cfg)
            except OSError as exc:
                log.debug("Zone %d reset error (zone may not exist): %s", i, exc)

    def read_chip_id(self) -> int:
        """Read and return the raw chip-ID byte from register 0x20."""
        assert self._bus is not None
        return self._bus.read_byte_data(self.addr, 0x20)


# ---------------------------------------------------------------------------
# USB HID controller for AORUS external devices
# ---------------------------------------------------------------------------

class AORUSHIDController:
    """
    Controls Gigabyte AORUS external RGB devices via USB HID.

    Targets all devices with VID 0x1044.  Each device receives the same
    64-byte HID output report; report format is community-derived from
    USB captures of Gigabyte Control Center.
    """

    HID_REPORT_SIZE = 64
    # HID command bytes (byte 0 of the 64-byte payload)
    CMD_SET_COLOR = 0x60
    CMD_SAVE      = 0x61

    def __init__(
        self,
        vendor_id:  int = USB_VID_GIGABYTE,
        product_id: Optional[int] = None,
    ):
        if not _HID_AVAILABLE:
            raise RuntimeError(
                "hid library not available. "
                "Install it: pip install hid  or  nix-shell -p python3Packages.hid"
            )
        self.vendor_id  = vendor_id
        self.product_id = product_id
        self._devices: list = []

    # ------------------------------------------------------------------
    def open(self) -> None:
        """Open all matching HID devices."""
        device_list = _hid_module.enumerate(self.vendor_id, self.product_id or 0)
        for info in device_list:
            try:
                dev = _hid_module.device()
                dev.open(info["vendor_id"], info["product_id"])
                dev.set_nonblocking(True)
                self._devices.append(dev)
                log.info(
                    "HID opened: %04X:%04X  %s %s",
                    info["vendor_id"], info["product_id"],
                    info.get("manufacturer_string", ""),
                    info.get("product_string", ""),
                )
            except OSError as exc:
                log.warning(
                    "HID: could not open %04X:%04X — %s",
                    info["vendor_id"], info["product_id"], exc,
                )

    def close(self) -> None:
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices.clear()

    def __enter__(self) -> "AORUSHIDController":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def device_count(self) -> int:
        return len(self._devices)

    # ------------------------------------------------------------------
    def _write_report(self, dev: object, payload: bytes) -> None:
        """
        Send a 64-byte HID output report.
        The report ID byte (0x00) is prepended as required by hidapi.
        """
        padded = (b"\x00" + payload + b"\x00" * self.HID_REPORT_SIZE)[
            : self.HID_REPORT_SIZE + 1
        ]
        dev.write(list(padded))   # type: ignore[attr-defined]

    def set_static_color(self, r: int, g: int, b: int) -> None:
        """Send a static color report to all open devices."""
        # Byte layout (community-derived):
        #   [0]  0x60  — set-color command
        #   [1]  0x01  — mode: static
        #   [2]  R
        #   [3]  G
        #   [4]  B
        #   [5..63] 0x00
        report = bytes([self.CMD_SET_COLOR, 0x01, r & 0xFF, g & 0xFF, b & 0xFF])
        report += b"\x00" * (self.HID_REPORT_SIZE - len(report))

        for dev in self._devices:
            try:
                self._write_report(dev, report)
                log.info("HID: set color #%02X%02X%02X", r, g, b)
            except OSError as exc:
                log.warning("HID write error: %s", exc)

    def set_effect(self, mode: str, r: int, g: int, b: int,
                   speed: int = 5, brightness: int = 9) -> None:
        """Send an effect report to all open devices."""
        mode_code = MODE_NAME_TO_CODE.get(mode.lower(), EFFECT_STATIC)
        speed_val = SPEED_TABLE[max(0, min(9, speed))]
        bri_val   = BRIGHTNESS_TABLE[max(0, min(9, brightness))]
        report = bytes([
            self.CMD_SET_COLOR, mode_code,
            r & 0xFF, g & 0xFF, b & 0xFF,
            speed_val, bri_val,
        ])
        report += b"\x00" * (self.HID_REPORT_SIZE - len(report))

        for dev in self._devices:
            try:
                self._write_report(dev, report)
            except OSError as exc:
                log.warning("HID write error: %s", exc)


# ---------------------------------------------------------------------------
# Top-level command implementations
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    """Scan and print all detected RGB devices."""
    print("=" * 60)
    print("  RGB Fusion — Device Scanner")
    print("=" * 60)

    # --- I2C / SMBus ---
    print("\n[I2C / SMBus  (motherboard LEDs)]")
    if not _SMBUS2_AVAILABLE:
        print("  smbus2 not installed — cannot scan I2C buses.")
        print("  Install: pip install smbus2")
    else:
        buses = find_rgb_i2c_buses()
        if buses:
            for bus_num, addr, chip in buses:
                print(f"  /dev/i2c-{bus_num}  addr=0x{addr:02X}  chip={chip}")
        else:
            print("  No ITE RGB controller found on any I2C bus.")
            print("  Check: modprobe i2c-dev i2c-i801 && i2cdetect -l")

    # --- USB HID ---
    print("\n[USB HID  (AORUS external devices, VID 0x1044)]")
    if not _HID_AVAILABLE:
        print("  hid library not installed — cannot scan USB devices.")
        print("  Install: pip install hid")
    else:
        found = _hid_module.enumerate(USB_VID_GIGABYTE, 0)
        if found:
            for info in found:
                pid  = info["product_id"]
                name = AORUS_PRODUCTS.get(pid, info.get("product_string", "unknown"))
                path = info.get("path", b"").decode(errors="replace")
                print(
                    f"  {info['vendor_id']:04X}:{pid:04X}  {name:<35}  {path}"
                )
        else:
            print("  No Gigabyte AORUS HID devices found.")

    print()


def _get_i2c_bus(forced_bus: Optional[int]) -> Tuple[int, int]:
    """Return (bus_num, i2c_addr) — auto-detect or use forced bus number."""
    if forced_bus is not None:
        # Assume standard address; probe to find the right one
        for addr in (I2C_ADDR_PRIMARY, I2C_ADDR_ALT):
            chip = _probe_i2c_addr(forced_bus, addr)
            if chip is not None:
                return forced_bus, addr
        log.warning(
            "No ITE chip responded on /dev/i2c-%d; "
            "using 0x%02X anyway.", forced_bus, I2C_ADDR_PRIMARY
        )
        return forced_bus, I2C_ADDR_PRIMARY

    buses = find_rgb_i2c_buses()
    if not buses:
        log.error(
            "No ITE RGB chip detected. "
            "Load kernel modules: modprobe i2c-dev i2c-i801\n"
            "Add your user to the i2c group: usermod -aG i2c $USER"
        )
        sys.exit(1)

    bus_num, addr, chip = buses[0]
    log.info("Auto-selected /dev/i2c-%d (chip=%s, addr=0x%02X)", bus_num, chip, addr)
    return bus_num, addr


def cmd_apply(config: FusionConfig, forced_bus: Optional[int] = None) -> None:
    """Apply a FusionConfig to the hardware."""
    if not config.zones:
        log.warning("Config has no zones defined; nothing to apply.")
        return

    bus_num, addr = _get_i2c_bus(forced_bus)
    with IT8295Controller(bus_num, addr) as ctrl:
        ctrl.set_zones(config.zones)

    log.info("Config applied successfully (%d zones).", len(config.zones))


# ---------------------------------------------------------------------------
# Daemon mode — watches config file and re-applies on changes
# ---------------------------------------------------------------------------

class RGBDaemon:
    """
    Watches a TOML config file for modification and re-applies the
    configuration to the hardware whenever the file changes.

    Responds to SIGTERM and SIGINT for clean shutdown.
    """

    POLL_INTERVAL_S = 1.0

    def __init__(self, config_path: Path, forced_bus: Optional[int] = None):
        self.config_path = config_path
        self.forced_bus  = forced_bus
        self._running    = False
        self._last_mtime = 0.0

    def _load_and_apply(self) -> None:
        try:
            cfg = FusionConfig.from_toml(self.config_path)
            cmd_apply(cfg, self.forced_bus)
        except Exception as exc:
            log.error("Failed to apply config: %s", exc)

    def run(self) -> None:
        log.info("Daemon started — watching %s", self.config_path)
        self._running = True

        def _stop(signum: int, _frame: object) -> None:
            log.info("Signal %d received; stopping daemon.", signum)
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT,  _stop)

        if self.config_path.exists():
            self._last_mtime = self.config_path.stat().st_mtime
            self._load_and_apply()
        else:
            log.warning("Config %s not found yet; waiting…", self.config_path)

        while self._running:
            time.sleep(self.POLL_INTERVAL_S)
            if not self.config_path.exists():
                continue
            mtime = self.config_path.stat().st_mtime
            if mtime != self._last_mtime:
                log.info("Config changed — re-applying…")
                self._last_mtime = mtime
                self._load_and_apply()

        log.info("Daemon stopped.")


# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------

def _parse_color(s: str) -> str:
    """Validate and normalise a color argument to 6-char uppercase hex."""
    raw = s.strip().lstrip("#")
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    if len(raw) == 8:          # 00RRGGBB — strip leading AA byte
        raw = raw[2:]
    if len(raw) != 6:
        raise argparse.ArgumentTypeError(
            f"Color '{s}' must be RRGGBB or 00RRGGBB hex (e.g. FF0000)."
        )
    try:
        int(raw, 16)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Color '{s}' contains invalid hex digits.")
    return raw.upper()


def _parse_level(s: str) -> int:
    """Parse an integer in 0-9 range."""
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{s}' is not a valid integer.")
    if not 0 <= v <= 9:
        raise argparse.ArgumentTypeError(f"{v} is out of range 0-9.")
    return v


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rgb-fusion",
        description="Control Gigabyte RGB Fusion LEDs on Linux/NixOS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rgb-fusion list
  rgb-fusion set --zone 0 --mode breath --color FF0000 --speed 5 --brightness 8
  rgb-fusion set-all --mode rainbow
  rgb-fusion apply --config /etc/rgb-fusion/config.toml
  rgb-fusion daemon --config /etc/rgb-fusion/config.toml
""",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--bus", type=int, default=None,
        metavar="N",
        help="Force I2C bus number (default: auto-detect)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ---- list ----
    sub.add_parser("list", help="List detected RGB devices")

    # ---- set ----
    p_set = sub.add_parser("set", help="Configure a single LED zone")
    p_set.add_argument("--zone", "-z", type=int, default=0, metavar="0-7",
                       help="Zone index (default: 0)")
    p_set.add_argument("--mode", "-m", default="static",
                       choices=sorted(MODE_NAME_TO_CODE),
                       help="LED effect mode (default: static)")
    p_set.add_argument("--color", "-c", type=_parse_color, default="FF0000",
                       metavar="RRGGBB",
                       help="Color as hex (default: FF0000)")
    p_set.add_argument("--speed", "-s", type=_parse_level, default=5, metavar="0-9",
                       help="Animation speed 0-9 (default: 5)")
    p_set.add_argument("--brightness", "-b", type=_parse_level, default=9, metavar="0-9",
                       help="Brightness 0-9 (default: 9)")
    p_set.add_argument("--led-count", type=int, default=DEFAULT_LED_COUNT,
                       metavar="N",
                       help=f"LEDs in ARGB strip (default: {DEFAULT_LED_COUNT})")

    # ---- set-all ----
    p_sa = sub.add_parser("set-all", help="Apply the same effect to all zones")
    p_sa.add_argument("--mode", "-m", default="static",
                      choices=sorted(MODE_NAME_TO_CODE))
    p_sa.add_argument("--color", "-c", type=_parse_color, default="FF0000",
                      metavar="RRGGBB")
    p_sa.add_argument("--speed", "-s", type=_parse_level, default=5, metavar="0-9")
    p_sa.add_argument("--brightness", "-b", type=_parse_level, default=9, metavar="0-9")

    # ---- apply ----
    p_apply = sub.add_parser("apply", help="Apply a TOML config file")
    p_apply.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                         metavar="PATH", help="Path to config.toml")

    # ---- daemon ----
    p_daemon = sub.add_parser(
        "daemon",
        help="Watch config file and re-apply on changes (for systemd)",
    )
    p_daemon.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                          metavar="PATH", help="Path to config.toml")

    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cmd = args.command

    if cmd == "list":
        cmd_list()

    elif cmd == "set":
        cfg = FusionConfig.from_cli(
            zone=args.zone,
            mode=args.mode,
            color=args.color,
            speed=args.speed,
            brightness=args.brightness,
            led_count=args.led_count,
        )
        cmd_apply(cfg, forced_bus=args.bus)

    elif cmd == "set-all":
        cfg = FusionConfig.all_zones(
            mode=args.mode,
            color=args.color,
            speed=args.speed,
            brightness=args.brightness,
        )
        cmd_apply(cfg, forced_bus=args.bus)

    elif cmd == "apply":
        cfg = FusionConfig.from_toml(args.config)
        cmd_apply(cfg, forced_bus=args.bus)

    elif cmd == "daemon":
        daemon = RGBDaemon(args.config, forced_bus=args.bus)
        daemon.run()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
