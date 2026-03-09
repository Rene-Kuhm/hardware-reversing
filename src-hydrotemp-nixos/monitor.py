#!/usr/bin/env python3
"""
PC Monitor NixOS Daemon
Sends hardware sensor data to a USB HID display (VID:0x3554, PID:0xFA09).

Protocol reverse-engineered from "PC Monitor All" .NET application.
HID report: 64 bytes, sent every 200ms.
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
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("pc-monitor")

# ---------------------------------------------------------------------------
# Device constants
# ---------------------------------------------------------------------------
VENDOR_ID        = 0x5131
PRODUCT_ID       = 0x2007
REPORT_ID        = 0x00
REPORT_LEN       = 64       # 64 bytes as-is (matches CyUSB raw USB transfer on Windows)
UPDATE_MS        = 200      # milliseconds between sends

# HID report header bytes
HEADER_B1  = 0x01
HEADER_B2  = 0x02

# SendValueArray indices  → byte offset in report (offset = index + 3)
IDX_CPU_TEMP   = 0
IDX_CPU_USAGE  = 1
IDX_CPU_POWER  = 2
IDX_CPU_FREQ   = 3
IDX_CPU_VOLT   = 4
IDX_GPU_TEMP   = 5
IDX_GPU_USAGE  = 6
IDX_GPU_POWER  = 7
IDX_GPU_FREQ   = 8
IDX_WC_FAN_RPM = 9
IDX_FAN_RPM    = 10
NUM_VALUES     = 11   # indices 0-10 are defined; up to 32 slots exist (bytes 3-35)


# ---------------------------------------------------------------------------
# Configurable max values (matches nud_Pic* controls in the original app)
# ---------------------------------------------------------------------------
@dataclass
class MaxValues:
    """Upper bounds used for 0-255 scaling.  Tune these for your hardware."""
    cpu_temp_c:     float = 100.0   # °C
    cpu_usage_pct:  float = 100.0   # %
    cpu_power_w:    float = 253.0   # W  (i7-14700F TDP ~253 W peak)
    cpu_freq_mhz:   float = 5600.0  # MHz (max boost for i7-14700F)
    cpu_volt_v:     float = 1.5     # V
    gpu_temp_c:     float = 110.0   # °C (RX 6600 XT throttle limit)
    gpu_usage_pct:  float = 100.0   # %
    gpu_power_w:    float = 160.0   # W  (RX 6600 XT TDP 160 W)
    gpu_freq_mhz:   float = 2589.0  # MHz (RX 6600 XT max boost)
    wc_fan_rpm:     float = 3000.0  # RPM
    fan_rpm:        float = 3000.0  # RPM


# ---------------------------------------------------------------------------
# Sensor reading helpers
# ---------------------------------------------------------------------------

def _read_file(path: str) -> Optional[str]:
    """Read a sysfs file, return stripped string or None on error."""
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


def _glob_first(pattern: str) -> Optional[str]:
    results = glob.glob(pattern)
    return results[0] if results else None


# ------------------------------------------------------------------
# CPU sensors (hwmon / coretemp / powercap)
# ------------------------------------------------------------------

def _find_hwmon_driver(driver_name: str) -> Optional[str]:
    """Return the first hwmon path whose 'name' file matches driver_name."""
    for p in glob.glob("/sys/class/hwmon/hwmon*/name"):
        name = _read_file(p)
        if name == driver_name:
            return os.path.dirname(p)
    return None


def read_cpu_temp_c() -> Optional[float]:
    """
    Try coretemp package temp first, then k10temp (AMD fallback),
    then any acpitz thermal zone.
    """
    # coretemp (Intel) – Package id 0 temp
    hwmon = _find_hwmon_driver("coretemp")
    if hwmon:
        for f in sorted(glob.glob(f"{hwmon}/temp*_label")):
            label = _read_file(f)
            if label and "package" in label.lower():
                input_f = f.replace("_label", "_input")
                val = _read_float(input_f, 1000.0)
                if val is not None:
                    return val

    # k10temp (AMD)
    hwmon = _find_hwmon_driver("k10temp")
    if hwmon:
        val = _read_float(f"{hwmon}/temp1_input", 1000.0)
        if val is not None:
            return val

    # Thermal zones fallback
    for tz in sorted(glob.glob("/sys/class/thermal/thermal_zone*/type")):
        ttype = _read_file(tz)
        if ttype in ("x86_pkg_temp", "acpitz", "cpu-thermal"):
            temp_f = os.path.join(os.path.dirname(tz), "temp")
            val = _read_float(temp_f, 1000.0)
            if val is not None:
                return val
    return None


def read_cpu_usage_pct() -> Optional[float]:
    """
    Parse /proc/stat for a single-shot CPU usage sample.
    We keep a module-level cache of the previous reading so that
    consecutive calls produce a meaningful delta.
    """
    stat = _read_file("/proc/stat")
    if stat is None:
        return None
    for line in stat.splitlines():
        if line.startswith("cpu "):
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq, steal
            vals = [int(x) for x in parts[1:]]
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

_cpu_usage_prev: dict = {}


def read_cpu_power_w() -> Optional[float]:
    """
    Use Intel RAPL via powercap, or hwmon power input.
    """
    # powercap RAPL – package-0 energy_uj
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
                    # handle counter wrap (max_energy_range_uj)
                    if de < 0:
                        max_f = os.path.join(os.path.dirname(pkg), "max_energy_range_uj")
                        max_e = _read_float(max_f) or 0.0
                        de += max_e
                    return de / dt / 1_000_000.0  # µJ/s → W
            return None

    # hwmon power fallback
    for p in glob.glob("/sys/class/hwmon/hwmon*/power1_input"):
        val = _read_float(p, 1_000_000.0)  # µW → W
        if val is not None:
            return val
    return None

_cpu_power_prev: dict = {}


def read_cpu_freq_mhz() -> Optional[float]:
    """Average across all CPUs from /proc/cpuinfo, fallback to cpufreq."""
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

    # cpufreq fallback: scaling_cur_freq (kHz → MHz)
    files = sorted(glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"))
    if files:
        vals = [_read_float(f, 1000.0) for f in files]
        vals = [v for v in vals if v is not None]
        if vals:
            return sum(vals) / len(vals)
    return None


def read_cpu_volt_v() -> Optional[float]:
    """
    CPU VCore from hwmon – typically exposed by the board's SIO chip
    (nct6775, it87, etc.) or coretemp.
    """
    for driver in ("nct6775", "nct6792", "nct6798", "it87", "w83627ehf"):
        hwmon = _find_hwmon_driver(driver)
        if hwmon:
            # Look for a voltage labelled vcore / vcpu
            for lf in glob.glob(f"{hwmon}/in*_label"):
                label = (_read_file(lf) or "").lower()
                if "vcore" in label or "vcpu" in label or "cpu" in label:
                    val = _read_float(lf.replace("_label", "_input"), 1000.0)
                    if val is not None:
                        return val
            # Fallback: in1 is often VCore on SuperIO chips
            val = _read_float(f"{hwmon}/in1_input", 1000.0)
            if val is not None:
                return val
    return None


# ------------------------------------------------------------------
# Fan RPM
# ------------------------------------------------------------------

def _read_fan_rpm(hwmon_path: str, fan_index: int = 1) -> Optional[float]:
    val = _read_float(f"{hwmon_path}/fan{fan_index}_input")
    return val


def read_fan_rpm() -> Optional[float]:
    """First available fan from any hwmon driver (system/case fan)."""
    for nf in sorted(glob.glob("/sys/class/hwmon/hwmon*/fan1_input")):
        val = _read_float(nf)
        if val is not None and val > 0:
            return val
    return None


def read_wc_fan_rpm() -> Optional[float]:
    """
    Water-cooling pump/fan RPM.  Tries fan2 on SuperIO first,
    then any fan that isn't fan1.
    """
    for driver in ("nct6775", "nct6792", "nct6798", "it87"):
        hwmon = _find_hwmon_driver(driver)
        if hwmon:
            for fan_idx in (2, 3, 4, 5):
                val = _read_float(f"{hwmon}/fan{fan_idx}_input")
                if val is not None and val > 0:
                    return val
    return None


# ------------------------------------------------------------------
# AMD GPU sensors (AMDGPU sysfs)  – primary for RX 6600 XT
# ------------------------------------------------------------------

def _find_amdgpu_hwmon() -> Optional[str]:
    for p in glob.glob("/sys/class/hwmon/hwmon*/name"):
        if _read_file(p) == "amdgpu":
            return os.path.dirname(p)
    return None


def _find_amdgpu_drm() -> Optional[str]:
    """Return first amdgpu DRM card sysfs path."""
    for dev in sorted(glob.glob("/sys/class/drm/card*/device/driver")):
        target = os.readlink(dev) if os.path.islink(dev) else ""
        if "amdgpu" in target:
            return os.path.dirname(dev)  # .../card0/device
    return None


def read_gpu_temp_c_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if not hwmon:
        return None
    # temp1 = edge, temp2 = junction (hotspot), temp3 = mem
    val = _read_float(f"{hwmon}/temp1_input", 1000.0)
    return val


def read_gpu_usage_pct_amd() -> Optional[float]:
    drm = _find_amdgpu_drm()
    if drm:
        val = _read_float(f"{drm}/gpu_busy_percent")
        if val is not None:
            return val
    # DRM debugfs fallback (requires root)
    for p in glob.glob("/sys/kernel/debug/dri/*/amdgpu_pm_info"):
        content = _read_file(p)
        if content:
            for line in content.splitlines():
                if "GPU Load" in line:
                    try:
                        return float(line.split(":")[1].strip().replace("%", ""))
                    except (ValueError, IndexError):
                        pass
    return None


def read_gpu_power_w_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if not hwmon:
        return None
    # power1_average (µW) — available on RDNA1/RDNA2 (RX 6600 XT)
    for fname in ("power1_average", "power1_input"):
        val = _read_float(f"{hwmon}/{fname}", 1_000_000.0)
        if val is not None:
            return val
    return None


def read_gpu_freq_mhz_amd() -> Optional[float]:
    hwmon = _find_amdgpu_hwmon()
    if hwmon:
        # freq1_input = SCLK in Hz on newer kernels
        val = _read_float(f"{hwmon}/freq1_input", 1_000_000.0)
        if val is not None:
            return val
    # pp_dpm_sclk: last line with * is active level
    drm = _find_amdgpu_drm()
    if drm:
        content = _read_file(f"{drm}/pp_dpm_sclk")
        if content:
            for line in reversed(content.splitlines()):
                if "*" in line:
                    # e.g.  "1: 2475Mhz *"
                    parts = line.replace("*", "").strip().split()
                    for p in parts:
                        p_clean = p.lower().replace("mhz", "")
                        try:
                            return float(p_clean)
                        except ValueError:
                            pass
    return None


# ------------------------------------------------------------------
# NVIDIA GPU sensors (nvidia-smi)  – fallback
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


def read_gpu_power_w_nvidia() -> Optional[float]:
    v = _nvidia_smi_query("power.draw")
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


def read_gpu_sensors(backend: str) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Returns (temp_c, usage_pct, power_w, freq_mhz)."""
    if backend == GpuBackend.AMD:
        return (
            read_gpu_temp_c_amd(),
            read_gpu_usage_pct_amd(),
            read_gpu_power_w_amd(),
            read_gpu_freq_mhz_amd(),
        )
    if backend == GpuBackend.NVIDIA:
        return (
            read_gpu_temp_c_nvidia(),
            read_gpu_usage_pct_nvidia(),
            read_gpu_power_w_nvidia(),
            read_gpu_freq_mhz_nvidia(),
        )
    return (None, None, None, None)


# ---------------------------------------------------------------------------
# HID report builder
# ---------------------------------------------------------------------------

def scale(value: Optional[float], max_value: float) -> int:
    """
    Scale a sensor value to 0-255.
    None / negative values map to 0.
    """
    if value is None or max_value <= 0:
        return 0
    clamped = max(0.0, min(value, max_value))
    return int(clamped / max_value * 255)


def build_report(
    cpu_temp:   Optional[float],
    cpu_usage:  Optional[float],
    cpu_power:  Optional[float],
    cpu_freq:   Optional[float],
    cpu_volt:   Optional[float],
    gpu_temp:   Optional[float],
    gpu_usage:  Optional[float],
    gpu_power:  Optional[float],
    gpu_freq:   Optional[float],
    wc_fan_rpm: Optional[float],
    fan_rpm:    Optional[float],
    mv: MaxValues,
) -> bytes:
    """
    Build the 64-byte HID output report.

    Layout:
      [0]       report ID  = 0x00
      [1]       header     = 0x01
      [2]       header     = 0x02
      [3..35]   SendValueArray[0..32]  (scaled sensor values)
      [36..63]  0x00 padding
    """
    send_values = [0] * 32  # slots 0-31 available; protocol uses 0-10

    send_values[IDX_CPU_TEMP]   = scale(cpu_temp,   mv.cpu_temp_c)
    send_values[IDX_CPU_USAGE]  = scale(cpu_usage,  mv.cpu_usage_pct)
    send_values[IDX_CPU_POWER]  = scale(cpu_power,  mv.cpu_power_w)
    send_values[IDX_CPU_FREQ]   = scale(cpu_freq,   mv.cpu_freq_mhz)
    send_values[IDX_CPU_VOLT]   = scale(cpu_volt,   mv.cpu_volt_v)
    send_values[IDX_GPU_TEMP]   = scale(gpu_temp,   mv.gpu_temp_c)
    send_values[IDX_GPU_USAGE]  = scale(gpu_usage,  mv.gpu_usage_pct)
    send_values[IDX_GPU_POWER]  = scale(gpu_power,  mv.gpu_power_w)
    send_values[IDX_GPU_FREQ]   = scale(gpu_freq,   mv.gpu_freq_mhz)
    send_values[IDX_WC_FAN_RPM] = scale(wc_fan_rpm, mv.wc_fan_rpm)
    send_values[IDX_FAN_RPM]    = scale(fan_rpm,    mv.fan_rpm)

    report = bytearray(REPORT_LEN)
    report[0] = REPORT_ID   # 0x00 – "no report ID" placeholder for hidapi
    report[1] = HEADER_B1   # 0x01
    report[2] = HEADER_B2   # 0x02
    for i, v in enumerate(send_values):
        report[3 + i] = v & 0xFF
    # bytes 35-64 remain 0x00 (padding already set by bytearray init)
    return bytes(report)


# ---------------------------------------------------------------------------
# HID device management
# ---------------------------------------------------------------------------

class HidDevice:
    """Wrapper around hid.Device with reconnection logic."""

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
                getattr(dev, "manufacturer", None) or "unknown manufacturer",
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
        """
        Send a HID output report.  Returns True on success.
        Closes the device handle on error so it is re-opened next cycle.
        """
        if self._dev is None:
            return False
        try:
            written = self._dev.write(report)
            if written < 0:
                log.warning("HID write returned %d – will reconnect", written)
                self.close()
                return False
            log.debug("HID write ok: %d bytes, report: %s", written, report.hex(" "))
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
    def __init__(self, mv: MaxValues, dry_run: bool = False, verbose: bool = False):
        self.mv      = mv
        self.dry_run = dry_run
        self.verbose = verbose
        self._running = True

        if not dry_run:
            self._hid = HidDevice(VENDOR_ID, PRODUCT_ID)
        else:
            self._hid = None  # type: ignore[assignment]

        self._gpu_backend: Optional[str] = None

    # ------------------------------------------------------------------
    def _detect_gpu(self) -> str:
        backend = detect_gpu_backend()
        log.info("GPU backend detected: %s", backend)
        return backend

    # ------------------------------------------------------------------
    def _collect(self) -> dict:
        cpu_temp  = read_cpu_temp_c()
        cpu_usage = read_cpu_usage_pct()
        cpu_power = read_cpu_power_w()
        cpu_freq  = read_cpu_freq_mhz()
        cpu_volt  = read_cpu_volt_v()
        wc_fan    = read_wc_fan_rpm()
        fan       = read_fan_rpm()

        if self._gpu_backend is None:
            self._gpu_backend = self._detect_gpu()

        gpu_temp, gpu_usage, gpu_power, gpu_freq = read_gpu_sensors(self._gpu_backend)

        return dict(
            cpu_temp=cpu_temp, cpu_usage=cpu_usage, cpu_power=cpu_power,
            cpu_freq=cpu_freq, cpu_volt=cpu_volt,
            gpu_temp=gpu_temp, gpu_usage=gpu_usage, gpu_power=gpu_power,
            gpu_freq=gpu_freq,
            wc_fan_rpm=wc_fan, fan_rpm=fan,
        )

    # ------------------------------------------------------------------
    def _log_sensors(self, sensors: dict):
        def fmt(v, unit=""):
            return f"{v:.1f}{unit}" if v is not None else "N/A"

        log.debug(
            "CPU: temp=%s usage=%s power=%s freq=%s volt=%s | "
            "GPU: temp=%s usage=%s power=%s freq=%s | "
            "FAN: wc=%s sys=%s",
            fmt(sensors["cpu_temp"], "°C"),
            fmt(sensors["cpu_usage"], "%"),
            fmt(sensors["cpu_power"], "W"),
            fmt(sensors["cpu_freq"], "MHz"),
            fmt(sensors["cpu_volt"], "V"),
            fmt(sensors["gpu_temp"], "°C"),
            fmt(sensors["gpu_usage"], "%"),
            fmt(sensors["gpu_power"], "W"),
            fmt(sensors["gpu_freq"], "MHz"),
            fmt(sensors["wc_fan_rpm"], "RPM"),
            fmt(sensors["fan_rpm"], "RPM"),
        )

    # ------------------------------------------------------------------
    def run(self):
        log.info(
            "PC Monitor daemon starting (VID=%04X PID=%04X, interval=%dms, dry_run=%s)",
            VENDOR_ID, PRODUCT_ID, UPDATE_MS, self.dry_run,
        )

        last_reconnect_attempt = 0.0
        last_open_logged = False

        while self._running:
            loop_start = time.monotonic()

            # ---- Collect sensors ----------------------------------------
            try:
                sensors = self._collect()
            except Exception as exc:
                log.error("Sensor collection error: %s", exc, exc_info=True)
                sensors = {k: None for k in (
                    "cpu_temp", "cpu_usage", "cpu_power", "cpu_freq", "cpu_volt",
                    "gpu_temp", "gpu_usage", "gpu_power", "gpu_freq",
                    "wc_fan_rpm", "fan_rpm",
                )}

            if self.verbose:
                self._log_sensors(sensors)

            # ---- Build report -------------------------------------------
            report = build_report(mv=self.mv, **sensors)

            # ---- Send ---------------------------------------------------
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
                    if not self._hid.send(report):
                        log.debug("Send failed – will retry next cycle")

            # ---- Sleep for remainder of interval ------------------------
            elapsed_ms = (time.monotonic() - loop_start) * 1000.0
            sleep_ms   = max(0.0, UPDATE_MS - elapsed_ms)
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        log.info("Daemon stopped.")
        if self._hid:
            self._hid.close()

    # ------------------------------------------------------------------
    def stop(self):
        log.info("Shutdown requested.")
        self._running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="PC Monitor NixOS – HID display daemon",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Collect sensors and print report without opening HID device")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Log sensor values every cycle")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Logging level (default: INFO)")

    # Max-value overrides (match original nud_Pic* controls)
    g = p.add_argument_group("sensor max values (for 0-255 scaling)")
    g.add_argument("--max-cpu-temp",    type=float, default=100.0, metavar="C")
    g.add_argument("--max-cpu-usage",   type=float, default=100.0, metavar="PCT")
    g.add_argument("--max-cpu-power",   type=float, default=253.0, metavar="W")
    g.add_argument("--max-cpu-freq",    type=float, default=5600.0, metavar="MHZ")
    g.add_argument("--max-cpu-volt",    type=float, default=1.5,   metavar="V")
    g.add_argument("--max-gpu-temp",    type=float, default=110.0, metavar="C")
    g.add_argument("--max-gpu-usage",   type=float, default=100.0, metavar="PCT")
    g.add_argument("--max-gpu-power",   type=float, default=160.0, metavar="W")
    g.add_argument("--max-gpu-freq",    type=float, default=2589.0, metavar="MHZ")
    g.add_argument("--max-wc-fan",      type=float, default=3000.0, metavar="RPM")
    g.add_argument("--max-fan",         type=float, default=3000.0, metavar="RPM")

    return p.parse_args()


def main():
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    mv = MaxValues(
        cpu_temp_c    = args.max_cpu_temp,
        cpu_usage_pct = args.max_cpu_usage,
        cpu_power_w   = args.max_cpu_power,
        cpu_freq_mhz  = args.max_cpu_freq,
        cpu_volt_v    = args.max_cpu_volt,
        gpu_temp_c    = args.max_gpu_temp,
        gpu_usage_pct = args.max_gpu_usage,
        gpu_power_w   = args.max_gpu_power,
        gpu_freq_mhz  = args.max_gpu_freq,
        wc_fan_rpm    = args.max_wc_fan,
        fan_rpm       = args.max_fan,
    )

    monitor = Monitor(mv=mv, dry_run=args.dry_run, verbose=args.verbose)

    def _sighandler(signum, frame):
        monitor.stop()

    signal.signal(signal.SIGTERM, _sighandler)
    signal.signal(signal.SIGINT,  _sighandler)

    monitor.run()


if __name__ == "__main__":
    main()
