#!/usr/bin/env python3
"""
PC Monitor NixOS Daemon
Sends hardware sensor data to the USB HID display VID:5131 PID:2007 ("FBB").

Protocol reverse-engineered from "PC Monitor All" .NET Windows application.
HID report: 65 bytes, sent every 200ms.

Report layout (65 bytes):
  [0]       0x00       HID Report ID
  [1..3]    00 01 02   Fixed header
  [4]       CPU core temp (°C, direct)
  [5]       GPU usage (%, direct 0-100)
  [6]       0x00       GPU power — firmware bug: must be 0
  [7]       CPU package power (W, direct)
  [8]       CPU hotspot/package temp (°C, direct)
  [9]       CPU max-thread usage (%, direct 0-100)
  [10]      GPU clock MHz ÷ 10
  [11]      CPU clock MHz ÷ 48
  [12]      0x01       constant
  [13]      CPU VID voltage × 100 (e.g. 1.05 V → 105)
  [14]      GPU temp (°C, direct)
  [15..18]  0x00       reserved
  [19]      0x0A       Celsius flag
  [20]      0x00       reserved
  [21]      CPU total average usage (%, direct 0-100)
  [22..23]  CPU fan RPM: high = RPM÷100, low = RPM%100
  [24..25]  Pump RPM:    high = RPM÷100, low = RPM%100
  [26..31]  Display config thresholds (fixed defaults)
  [32]      Rolling counter (~1 per 3 packets)
  [33]      0x06       constant
  [34]      0x19       constant
  [35..64]  0x00       padding
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
UPDATE_MS  = 200


# ---------------------------------------------------------------------------
# Sensor reading helpers
# ---------------------------------------------------------------------------

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
    for p in glob.glob("/sys/class/hwmon/hwmon*/name"):
        if _read_file(p) == driver_name:
            return os.path.dirname(p)
    return None


# ------------------------------------------------------------------
# CPU sensors
# ------------------------------------------------------------------

def read_cpu_temp_c() -> Optional[float]:
    hwmon = _find_hwmon_driver("coretemp")
    if hwmon:
        for f in sorted(glob.glob(f"{hwmon}/temp*_label")):
            label = _read_file(f)
            if label and "package" in label.lower():
                val = _read_float(f.replace("_label", "_input"), 1000.0)
                if val is not None:
                    return val

    hwmon = _find_hwmon_driver("k10temp")
    if hwmon:
        val = _read_float(f"{hwmon}/temp1_input", 1000.0)
        if val is not None:
            return val

    for tz in sorted(glob.glob("/sys/class/thermal/thermal_zone*/type")):
        ttype = _read_file(tz)
        if ttype in ("x86_pkg_temp", "acpitz", "cpu-thermal"):
            val = _read_float(os.path.join(os.path.dirname(tz), "temp"), 1000.0)
            if val is not None:
                return val
    return None


def read_cpu_hotspot_c() -> Optional[float]:
    hwmon = _find_hwmon_driver("k10temp")
    if hwmon:
        for path in (f"{hwmon}/temp2_input", f"{hwmon}/temp3_input"):
            val = _read_float(path, 1000.0)
            if val is not None:
                return val
        val = _read_float(f"{hwmon}/temp1_input", 1000.0)
        if val is not None:
            return val

    hwmon = _find_hwmon_driver("coretemp")
    if hwmon:
        for f in sorted(glob.glob(f"{hwmon}/temp*_label")):
            label = _read_file(f)
            if label and "package" in label.lower():
                val = _read_float(f.replace("_label", "_input"), 1000.0)
                if val is not None:
                    return val
    return read_cpu_temp_c()


_cpu_usage_prev: dict = {}


def read_cpu_usage_pct() -> Optional[float]:
    stat = _read_file("/proc/stat")
    if stat is None:
        return None
    for line in stat.splitlines():
        if line.startswith("cpu "):
            parts = line.split()
            vals  = [int(x) for x in parts[1:]]
            idle  = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            prev  = _cpu_usage_prev.get("data")
            _cpu_usage_prev["data"] = (idle, total)
            if prev is None:
                return 0.0
            d_idle  = idle  - prev[0]
            d_total = total - prev[1]
            if d_total == 0:
                return 0.0
            return max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))
    return None


def read_cpu_max_thread_pct() -> Optional[float]:
    try:
        with open("/proc/stat") as f:
            lines = f.readlines()
    except OSError:
        return None

    max_usage = 0.0
    for line in lines:
        if line.startswith("cpu") and line[3].isdigit():
            parts = line.split()
            vals  = [int(x) for x in parts[1:]]
            idle  = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            key   = parts[0]
            prev  = _cpu_usage_prev.get(key)
            _cpu_usage_prev[key] = (idle, total)
            if prev:
                d_idle  = idle  - prev[0]
                d_total = total - prev[1]
                if d_total > 0:
                    usage = max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))
                    max_usage = max(max_usage, usage)
    return max_usage if max_usage > 0.0 else read_cpu_usage_pct()


_cpu_power_prev: dict = {}


def read_cpu_power_w() -> Optional[float]:
    for pkg in sorted(glob.glob("/sys/class/powercap/intel-rapl/intel-rapl:*/name")):
        name = _read_file(pkg)
        if name and "package" in name.lower():
            energy_f = os.path.join(os.path.dirname(pkg), "energy_uj")
            prev_key = f"rapl_{pkg}"
            now      = time.monotonic()
            energy   = _read_float(energy_f)
            prev     = _cpu_power_prev.get(prev_key)
            _cpu_power_prev[prev_key] = (now, energy)
            if prev and energy is not None:
                dt = now - prev[0]
                if dt > 0:
                    de = energy - prev[1]
                    if de < 0:
                        max_f = os.path.join(os.path.dirname(pkg), "max_energy_range_uj")
                        de += _read_float(max_f) or 0.0
                    return de / dt / 1_000_000.0
            return None

    for p in glob.glob("/sys/class/hwmon/hwmon*/power1_input"):
        val = _read_float(p, 1_000_000.0)
        if val is not None:
            return val
    return None


def read_cpu_freq_mhz() -> Optional[float]:
    cpuinfo = _read_file("/proc/cpuinfo")
    if cpuinfo:
        freqs = []
        for line in cpuinfo.splitlines():
            if line.startswith("cpu MHz"):
                try:
                    freqs.append(float(line.split(":")[1].strip()))
                except (ValueError, IndexError):
                    pass
        if freqs:
            return sum(freqs) / len(freqs)

    files = sorted(glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"))
    if files:
        vals = [_read_float(f, 1000.0) for f in files]
        vals = [v for v in vals if v is not None]
        if vals:
            return sum(vals) / len(vals)
    return None


def read_cpu_volt_v() -> Optional[float]:
    for driver in ("nct6775", "nct6792", "nct6798", "it87", "w83627ehf"):
        hwmon = _find_hwmon_driver(driver)
        if hwmon:
            for lf in glob.glob(f"{hwmon}/in*_label"):
                label = (_read_file(lf) or "").lower()
                if "vcore" in label or "vcpu" in label or "cpu" in label:
                    val = _read_float(lf.replace("_label", "_input"), 1000.0)
                    if val is not None:
                        return val
            val = _read_float(f"{hwmon}/in1_input", 1000.0)
            if val is not None:
                return val
    return None


# ------------------------------------------------------------------
# Fan / pump RPM
# ------------------------------------------------------------------

def read_fan_rpm() -> Optional[float]:
    zero_rpm: Optional[float] = None
    for nf in sorted(glob.glob("/sys/class/hwmon/hwmon*/fan*_input")):
        val = _read_float(nf)
        if val is not None and val > 0:
            return val
        if val == 0:
            zero_rpm = 0.0
    return zero_rpm


def read_pump_rpm() -> Optional[float]:
    for driver in ("nct6775", "nct6792", "nct6798", "it87"):
        hwmon = _find_hwmon_driver(driver)
        if hwmon:
            for fan_idx in (2, 3, 4, 5):
                val = _read_float(f"{hwmon}/fan{fan_idx}_input")
                if val is not None and val > 0:
                    return val
    return read_fan_rpm()


# ------------------------------------------------------------------
# AMD GPU sensors
# ------------------------------------------------------------------

def _find_amdgpu_hwmon() -> Optional[str]:
    for p in glob.glob("/sys/class/hwmon/hwmon*/name"):
        if _read_file(p) == "amdgpu":
            return os.path.dirname(p)
    return None


def _find_amdgpu_drm() -> Optional[str]:
    for dev in sorted(glob.glob("/sys/class/drm/card*/device/driver")):
        target = os.readlink(dev) if os.path.islink(dev) else ""
        if "amdgpu" in target:
            return os.path.dirname(dev)
    return None


def read_gpu_temp_c_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if not hwmon:
        return None
    return _read_float(f"{hwmon}/temp1_input", 1000.0)


def read_gpu_usage_pct_amd() -> Optional[float]:
    drm = _find_amdgpu_drm()
    if drm:
        val = _read_float(f"{drm}/gpu_busy_percent")
        if val is not None:
            return val
    return None


def read_gpu_freq_mhz_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if hwmon:
        val = _read_float(f"{hwmon}/freq1_input", 1_000_000.0)
        if val is not None:
            return val
    drm = _find_amdgpu_drm()
    if drm:
        content = _read_file(f"{drm}/pp_dpm_sclk")
        if content:
            for line in reversed(content.splitlines()):
                if "*" in line:
                    for part in line.replace("*", "").strip().split():
                        try:
                            return float(part.lower().replace("mhz", ""))
                        except ValueError:
                            pass
    return None


# ------------------------------------------------------------------
# NVIDIA GPU sensors
# ------------------------------------------------------------------

def _nvidia_smi_query(field: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def read_gpu_temp_c_nvidia() -> Optional[float]:
    v = _nvidia_smi_query("temperature.gpu")
    return float(v) if v else None


def read_gpu_usage_pct_nvidia() -> Optional[float]:
    v = _nvidia_smi_query("utilization.gpu")
    return float(v) if v else None


def read_gpu_freq_mhz_nvidia() -> Optional[float]:
    v = _nvidia_smi_query("clocks.gr")
    return float(v) if v else None


# ------------------------------------------------------------------
# GPU dispatcher
# ------------------------------------------------------------------

class GpuBackend:
    AMD    = "amd"
    NVIDIA = "nvidia"
    NONE   = "none"


def detect_gpu_backend() -> str:
    if _find_amdgpu_hwmon():
        return GpuBackend.AMD
    if _nvidia_smi_query("name") is not None:
        return GpuBackend.NVIDIA
    return GpuBackend.NONE


def read_gpu_sensors(backend: str) -> tuple:
    """Returns (temp_c, usage_pct, freq_mhz)."""
    if backend == GpuBackend.AMD:
        return (read_gpu_temp_c_amd(), read_gpu_usage_pct_amd(), read_gpu_freq_mhz_amd())
    if backend == GpuBackend.NVIDIA:
        return (read_gpu_temp_c_nvidia(), read_gpu_usage_pct_nvidia(), read_gpu_freq_mhz_nvidia())
    return (None, None, None)


# ---------------------------------------------------------------------------
# HID report builder — protocol for VID:5131 PID:2007
# ---------------------------------------------------------------------------

def _clamp_int(value: Optional[float], lo: int = 0, hi: int = 255) -> int:
    if value is None:
        return 0
    return max(lo, min(hi, int(value)))


def _rpm_bytes(rpm: Optional[float]) -> tuple:
    r = max(0, min(25500, int(rpm or 0)))
    return r // 100, r % 100


def build_report(
    cpu_temp_c:         Optional[float],
    cpu_hotspot_c:      Optional[float],
    cpu_power_w:        Optional[float],
    cpu_freq_mhz:       Optional[float],
    cpu_volt_v:         Optional[float],
    cpu_usage_pct:      Optional[float],
    cpu_max_thread_pct: Optional[float],
    gpu_temp_c:         Optional[float],
    gpu_usage_pct:      Optional[float],
    gpu_freq_mhz:       Optional[float],
    fan_rpm:            Optional[float],
    pump_rpm:           Optional[float],
    counter:            int = 0,
) -> bytes:
    buf = bytearray(REPORT_LEN)

    # Header
    buf[0] = 0x00
    buf[1] = 0x00
    buf[2] = 0x01
    buf[3] = 0x02

    # Sensors
    buf[4]  = _clamp_int(cpu_temp_c)
    buf[5]  = _clamp_int(gpu_usage_pct, 0, 100)
    buf[6]  = 0x00  # GPU power: firmware bug — must stay 0
    buf[7]  = _clamp_int(cpu_power_w)
    buf[8]  = _clamp_int(cpu_hotspot_c)
    buf[9]  = _clamp_int(cpu_max_thread_pct, 0, 100)
    buf[10] = _clamp_int((gpu_freq_mhz or 0) / 10)
    buf[11] = _clamp_int((cpu_freq_mhz or 0) / 48)
    buf[12] = 0x01
    buf[13] = _clamp_int((cpu_volt_v or 0) * 100)
    buf[14] = _clamp_int(gpu_temp_c)

    # buf[15..18] = 0x00 (already zero)
    buf[19] = 0x0A  # Celsius flag
    # buf[20] = 0x00

    buf[21] = _clamp_int(cpu_usage_pct, 0, 100)

    fan_hi, fan_lo = _rpm_bytes(fan_rpm)
    buf[22] = fan_hi
    buf[23] = fan_lo

    pmp_hi, pmp_lo = _rpm_bytes(pump_rpm)
    buf[24] = pmp_hi
    buf[25] = pmp_lo

    # Display config thresholds (fixed defaults from protocol analysis)
    buf[26] = 0x14
    buf[27] = 0x1A
    buf[28] = 0x03
    buf[29] = 0x0E
    buf[30] = 0x12
    buf[31] = 0x19

    buf[32] = counter & 0xFF
    buf[33] = 0x06
    buf[34] = 0x19

    # buf[35..64] = 0x00 padding (already zero)
    return bytes(buf)


# ---------------------------------------------------------------------------
# HID device wrapper
# ---------------------------------------------------------------------------

class HidDevice:
    def __init__(self, vid: int, pid: int, reconnect_delay: float = 5.0):
        self.vid             = vid
        self.pid             = pid
        self.reconnect_delay = reconnect_delay
        self._dev: Optional[hid.Device] = None

    def _open(self) -> bool:
        try:
            dev = hid.Device(self.vid, self.pid)
            dev.nonblocking = True
            self._dev = dev
            log.info(
                "Opened HID device %04X:%04X – %s",
                self.vid, self.pid,
                getattr(dev, "product", None) or "unknown",
            )
            return True
        except Exception as exc:
            log.debug("Cannot open HID device: %s", exc)
            self._dev = None
            return False

    def ensure_open(self) -> bool:
        if self._dev is not None:
            return True
        return self._open()

    def send(self, report: bytes) -> bool:
        if self._dev is None:
            return False
        try:
            written = self._dev.write(report)
            if written < 0:
                log.warning("HID write returned %d – will reconnect", written)
                self.close()
                return False
            log.debug("HID write ok: %d bytes", written)
            return True
        except Exception as exc:
            log.warning("HID write error (%s) – will reconnect", exc)
            self.close()
            return False

    def close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None


# ---------------------------------------------------------------------------
# Main daemon
# ---------------------------------------------------------------------------

class Monitor:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run  = dry_run
        self.verbose  = verbose
        self._running = True
        self._counter = 0
        self._counter_tick = 0

        if not dry_run:
            self._hid = HidDevice(VENDOR_ID, PRODUCT_ID)
        else:
            self._hid = None  # type: ignore[assignment]

        self._gpu_backend: Optional[str] = None

    def _detect_gpu(self) -> str:
        backend = detect_gpu_backend()
        log.info("GPU backend detected: %s", backend)
        return backend

    def _collect(self) -> dict:
        if self._gpu_backend is None:
            self._gpu_backend = self._detect_gpu()

        gpu_temp, gpu_usage, gpu_freq = read_gpu_sensors(self._gpu_backend)

        return dict(
            cpu_temp_c         = read_cpu_temp_c(),
            cpu_hotspot_c      = read_cpu_hotspot_c(),
            cpu_power_w        = read_cpu_power_w(),
            cpu_freq_mhz       = read_cpu_freq_mhz(),
            cpu_volt_v         = read_cpu_volt_v(),
            cpu_usage_pct      = read_cpu_usage_pct(),
            cpu_max_thread_pct = read_cpu_max_thread_pct(),
            gpu_temp_c         = gpu_temp,
            gpu_usage_pct      = gpu_usage,
            gpu_freq_mhz       = gpu_freq,
            fan_rpm            = read_fan_rpm(),
            pump_rpm           = read_pump_rpm(),
        )

    def _log_sensors(self, s: dict):
        def fmt(v, unit=""):
            return f"{v:.1f}{unit}" if v is not None else "N/A"
        log.debug(
            "CPU: temp=%s hotspot=%s power=%s freq=%s volt=%s usage=%s maxthread=%s | "
            "GPU: temp=%s usage=%s freq=%s | FAN: fan=%s pump=%s",
            fmt(s["cpu_temp_c"], "°C"), fmt(s["cpu_hotspot_c"], "°C"),
            fmt(s["cpu_power_w"], "W"),  fmt(s["cpu_freq_mhz"], "MHz"),
            fmt(s["cpu_volt_v"], "V"),   fmt(s["cpu_usage_pct"], "%"),
            fmt(s["cpu_max_thread_pct"], "%"),
            fmt(s["gpu_temp_c"], "°C"),  fmt(s["gpu_usage_pct"], "%"),
            fmt(s["gpu_freq_mhz"], "MHz"),
            fmt(s["fan_rpm"], "RPM"),    fmt(s["pump_rpm"], "RPM"),
        )

    def _next_counter(self) -> int:
        self._counter_tick += 1
        if self._counter_tick >= 3:
            self._counter_tick = 0
            self._counter = (self._counter + 1) & 0xFF
        return self._counter

    def run(self):
        log.info(
            "PC Monitor daemon starting (VID=%04X PID=%04X, interval=%dms, dry_run=%s)",
            VENDOR_ID, PRODUCT_ID, UPDATE_MS, self.dry_run,
        )

        last_reconnect_attempt = 0.0
        last_open_logged = False

        while self._running:
            loop_start = time.monotonic()

            try:
                sensors = self._collect()
            except Exception as exc:
                log.error("Sensor collection error: %s", exc, exc_info=True)
                sensors = {k: None for k in (
                    "cpu_temp_c", "cpu_hotspot_c", "cpu_power_w", "cpu_freq_mhz",
                    "cpu_volt_v", "cpu_usage_pct", "cpu_max_thread_pct",
                    "gpu_temp_c", "gpu_usage_pct", "gpu_freq_mhz",
                    "fan_rpm", "pump_rpm",
                )}

            if self.verbose:
                self._log_sensors(sensors)

            report = build_report(**sensors, counter=self._next_counter())

            if self.dry_run:
                log.info("DRY-RUN report: %s", report.hex(" "))
            else:
                now = time.monotonic()
                if not self._hid.ensure_open():
                    if now - last_reconnect_attempt >= self._hid.reconnect_delay:
                        last_reconnect_attempt = now
                        if not last_open_logged:
                            log.warning(
                                "HID device %04X:%04X not found – retrying every %.0fs",
                                VENDOR_ID, PRODUCT_ID, self._hid.reconnect_delay,
                            )
                            last_open_logged = True
                else:
                    last_open_logged = False
                    self._hid.send(report)

            elapsed_ms = (time.monotonic() - loop_start) * 1000.0
            sleep_ms   = max(0.0, UPDATE_MS - elapsed_ms)
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        log.info("Daemon stopped.")
        if self._hid:
            self._hid.close()

    def stop(self):
        log.info("Shutdown requested.")
        self._running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="PC Monitor NixOS – HID display daemon (VID:5131 PID:2007)"
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Collect sensors and print report without opening HID device")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Log sensor values every cycle")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main():
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    monitor = Monitor(dry_run=args.dry_run, verbose=args.verbose)

    def _sighandler(signum, frame):
        monitor.stop()

    signal.signal(signal.SIGTERM, _sighandler)
    signal.signal(signal.SIGINT,  _sighandler)

    monitor.run()


if __name__ == "__main__":
    main()
