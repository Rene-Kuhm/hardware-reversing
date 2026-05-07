#!/usr/bin/env python3
"""
PC Monitor Arch Linux – HID display daemon for VID:5131 PID:2007
Adaptado de Datos-xyz-ydrotemp para Arch/CachyOS
"""
import hid
import time
import logging
import os
import glob
import subprocess
import sys
import signal
import argparse
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("pc-monitor")

VENDOR_ID  = 0x5131
PRODUCT_ID = 0x2007
REPORT_LEN = 65
UPDATE_MS = 200


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


def _read_float(path: str, divisor: float = 1.0) -> Optional[float]:
    raw = _read_file(path)
    if raw is None:
        return None
    try:
        return float(raw) / divisor
    except ValueError:
        return None


def _find_hwmon_driver(driver_name: str) -> Optional[str]:
    for p in glob.iglob("/sys/class/hwmon/hwmon*/name"):
        if _read_file(p) == driver_name:
            return os.path.dirname(p)
    return None


def read_cpu_temp_c() -> Optional[float]:
    hwmon = _find_hwmon_driver("coretemp")
    if hwmon:
        for f in sorted(glob.iglob(f"{hwmon}/temp*_label")):
            label = _read_file(f)
            if label and "package" in label.lower():
                val = _read_float(f.replace("_label", "_input"), 1_000.0)
                if val is not None:
                    return val
    return None


_cpu_usage_prev = {}


def read_cpu_usage_pct() -> Optional[float]:
    stat = _read_file("/proc/stat")
    if stat is None:
        return None
    for line in stat.splitlines():
        if line.startswith("cpu "):
            parts = line.split()
            vals = [int(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            prev = _cpu_usage_prev.get("data")
            _cpu_usage_prev["data"] = (idle, total)
            if prev is None:
                return 0.0
            d_idle = idle - prev[0]
            d_total = total - prev[1]
            if d_total == 0:
                return 0.0
            return max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))
    return None


def read_fan_rpm() -> Optional[float]:
    zero_rpm: Optional[float] = None
    for nf in sorted(glob.iglob("/sys/class/hwmon/hwmon*/fan*_input")):
        val = _read_float(nf)
        if val is not None and val > 0:
            return val
        if val == 0:
            zero_rpm = 0.0
    return zero_rpm


def read_pump_rpm() -> Optional[float]:
    for driver in ("nct6775", "nct6798", "nct67", "it87"):
        hwmon = _find_hwmon_driver(driver)
        if hwmon:
            for fan_idx in (2, 3, 4, 5):
                val = _read_float(f"{hwmon}/fan{fan_idx}_input")
                if val is not None and val > 0:
                    return val
    return read_fan_rpm()


def _find_amdgpu_hwmon() -> Optional[str]:
    for p in glob.iglob("/sys/class/hwmon/hwmon*/name"):
        if _read_file(p) == "amdgpu":
            return os.path.dirname(p)
    return None


def read_gpu_temp_c_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if hwmon:
        return _read_float(f"{hwmon}/temp1_input", 1_000.0)
    return None


def read_gpu_usage_pct_amd() -> Optional[float]:
    for dev in sorted(glob.iglob("/sys/class/drm/card*/device/gpu_busy_percent")):
        val = _read_float(dev)
        if val is not None:
            return val
    return None


def _clamp_int(value: Optional[float], lo: int = 0, hi: int = 255) -> int:
    if value is None:
        return 0
    return max(lo, min(hi, int(value)))


def _rpm_bytes(rpm: Optional[float]) -> tuple:
    r = max(0, min(25500, int(rpm or 0)))
    return r // 100, r % 100


def build_report(
    cpu_temp_c: Optional[float],
    cpu_hotspot_c: Optional[float],
    cpu_usage_pct: Optional[float],
    gpu_temp_c: Optional[float],
    gpu_usage_pct: Optional[float],
    fan_rpm: Optional[float],
    pump_rpm: Optional[float],
    counter: int = 0,
) -> bytes:
    buf = bytearray(REPORT_LEN)

    buf[0] = 0x00
    buf[1] = 0x00
    buf[2] = 0x01
    buf[3] = 0x02

    buf[4] = _clamp_int(cpu_temp_c)
    buf[5] = _clamp_int(gpu_usage_pct, 0, 100)
    buf[6] = 0x00
    buf[7] = _clamp_int(cpu_usage_pct)
    buf[8] = _clamp_int(cpu_hotspot_c)
    buf[9] = _clamp_int(cpu_usage_pct, 0, 100)
    buf[10] = 0x01
    buf[11] = 0x64
    buf[14] = _clamp_int(gpu_temp_c)

    buf[19] = 0x0A
    buf[21] = _clamp_int(cpu_usage_pct, 0, 100)

    fan_hi, fan_lo = _rpm_bytes(fan_rpm)
    buf[22] = fan_hi
    buf[23] = fan_lo

    pmp_hi, pmp_lo = _rpm_bytes(pump_rpm)
    buf[24] = pmp_hi
    buf[25] = pmp_lo

    buf[26] = 0x14
    buf[27] = 0x1A
    buf[28] = 0x03
    buf[29] = 0x0E
    buf[30] = 0x12
    buf[31] = 0x19

    buf[32] = counter & 0xFF
    buf[33] = 0x06
    buf[34] = 0x19

    return bytes(buf)


class HidDevice:
    def __init__(self, vid: int, pid: int):
        self.vid = vid
        self.pid = pid
        self._dev = None

    def open(self) -> bool:
        try:
            self._dev = hid.Device(self.vid, self.pid)
            self._dev.nonblocking = True
            log.info("Opened HID device %04X:%04X", self.vid, self.pid)
            return True
        except Exception as exc:
            log.debug("Cannot open HID device: %s", exc)
            self._dev = None
            return False

    def send(self, report: bytes) -> bool:
        if self._dev is None:
            return False
        try:
            self._dev.write(report)
            return True
        except Exception as exc:
            log.warning("HID write error: %s", exc)
            self._dev = None
            return False

    def close(self):
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None


class Monitor:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self._running = True
        self._counter = 0
        self._counter_tick = 0
        self._hid = None if dry_run else HidDevice(VENDOR_ID, PRODUCT_ID)

    def run(self):
        log.info("PC Monitor daemon starting (VID=%04X PID=%04X)", VENDOR_ID, PRODUCT_ID)

        while self._running:
            loop_start = time.monotonic()

            cpu_temp = read_cpu_temp_c()
            cpu_usage = read_cpu_usage_pct()
            gpu_temp = read_gpu_temp_c_amd()
            gpu_usage = read_gpu_usage_pct_amd()
            fan_rpm = read_fan_rpm()
            pump_rpm = read_pump_rpm()

            if self.verbose:
                log.info(
                    "CPU: %s°C | GPU: %s°C | FAN: %s RPM | PUMP: %s RPM",
                    cpu_temp, gpu_temp, fan_rpm, pump_rpm
                )

            self._counter_tick += 1
            if self._counter_tick >= 3:
                self._counter_tick = 0
                self._counter = (self._counter + 1) & 0xFF

            report = build_report(
                cpu_temp, cpu_temp, cpu_usage,
                gpu_temp, gpu_usage,
                fan_rpm, pump_rpm,
                self._counter
            )

            if self.dry_run:
                log.info("DRY-RUN: %s", report.hex(" "))
            elif self._hid:
                if not self._hid.open():
                    time.sleep(5)
                else:
                    self._hid.send(report)

            elapsed = (time.monotonic() - loop_start) * 1000.0
            sleep_ms = max(0.0, UPDATE_MS - elapsed)
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        if self._hid:
            self._hid.close()

    def stop(self):
        self._running = False


def main():
    parser = argparse.ArgumentParser(description="PC Monitor HID display daemon")
    parser.add_argument("--dry-run", action="store_true", help="Print without HID device")
    parser.add_argument("--verbose", "-v", action="store_true", help="Log sensor values")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    monitor = Monitor(dry_run=args.dry_run, verbose=args.verbose)

    signal.signal(signal.SIGTERM, lambda s, f: monitor.stop())
    signal.signal(signal.SIGINT, lambda s, f: monitor.stop())

    monitor.run()


if __name__ == "__main__":
    main()