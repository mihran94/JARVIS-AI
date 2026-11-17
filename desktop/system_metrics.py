"""Read local OS counters for the desktop HUD without opening network connections.

The GPU and the CPU temperature come from the Mark LVI source
(`actions/system_monitor.py`), which reads NVML through ctypes and the
temperature through psutil, so no subprocess is started and nothing is
guessed. A value that cannot be read stays unavailable; it is never faked.
"""
import ctypes
import os
from pathlib import Path
import platform
import shutil

import psutil


class CpuSampler:
    """Use the first non-blocking read as the baseline for subsequent samples."""

    def __init__(self):
        self.ready = False

    def sample(self):
        try:
            usage = psutil.cpu_percent(interval=None)
        except (OSError, RuntimeError, psutil.Error):
            self.ready = False
            return None
        was_ready = self.ready
        self.ready = True
        return usage if was_ready else None


def _gib(value):
    return round(value / (1024 ** 3), 1)


#: The NVML library, once it has been found. None means "not tried yet".
_nvml_lib = None
_nvml_state = None


def _nvml_gpu() -> float:
    """The GPU load in percent, or -1.0 when there is no readable GPU.

    NVML is read through ctypes, so no process is started. Windows loads
    nvml.dll, the other platforms load the shared library.
    """
    global _nvml_lib, _nvml_state
    if _nvml_state is False:
        return -1.0
    try:
        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            if platform.system() == "Windows":
                names = ("nvml", r"C:\Windows\System32\nvml.dll")
                load = ctypes.WinDLL
            else:
                names = ("libnvidia-ml.so.1", "libnvidia-ml.so", "libnvidia-ml.dylib")
                load = ctypes.CDLL
            for name in names:
                try:
                    library = load(name)
                    library.nvmlInit_v2()
                    _nvml_lib = library
                    break
                except Exception:
                    continue
        if _nvml_lib is None:
            _nvml_state = False
            return -1.0
        _nvml_state = True
        library = _nvml_lib
        handle = _Util()
        library.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle))
        rates = _Util()
        library.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(rates))
        return float(rates.gpu)
    except Exception:
        return -1.0


def _cpu_temperature() -> float:
    """The CPU temperature in Celsius, or -1.0 when it cannot be read."""
    try:
        temperatures = psutil.sensors_temperatures()
        for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz",
                     "cpu-thermal", "zenpower", "it8688"):
            if name in temperatures and temperatures[name]:
                return float(temperatures[name][0].current)
        for entries in temperatures.values():
            if entries:
                return float(entries[0].current)
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            import wmi  # type: ignore
            readings = wmi.WMI(namespace="root/wmi").MSAcpi_ThermalZoneTemperature()
            if readings:
                return (readings[0].CurrentTemperature / 10.0) - 273.15
        except Exception:
            pass
    return -1.0


def snapshot(path=None, cpu_sampler=None):
    """Return basic metrics or explicit unavailable values; never guess CPU load."""
    root = Path(path or Path.home())
    data = {
        "cpu_cores": os.cpu_count(),
        "cpu_usage_percent": cpu_sampler.sample() if cpu_sampler is not None else None,
        "ram_usage_percent": None,
        "ram_used_gib": None,
        "ram_total_gib": None,
        "disk_used_gib": None,
        "disk_total_gib": None,
        "network_status": "Not measured",
        "gpu_usage_percent": None,
        "cpu_temperature_c": None,
    }
    try:
        usage = shutil.disk_usage(root)
        data["disk_used_gib"] = _gib(usage.used)
        data["disk_total_gib"] = _gib(usage.total)
    except (OSError, ValueError):
        pass
    try:
        memory = psutil.virtual_memory()
        data["ram_usage_percent"] = memory.percent
        data["ram_used_gib"] = _gib(memory.total - memory.available)
        data["ram_total_gib"] = _gib(memory.total)
    except (OSError, RuntimeError, psutil.Error):
        pass
    gpu = _nvml_gpu()
    if gpu >= 0:
        data["gpu_usage_percent"] = round(gpu, 1)
    temperature = _cpu_temperature()
    if temperature > -1:
        data["cpu_temperature_c"] = round(temperature, 1)
    return data


def format_snapshot(data):
    def ratio(used, total):
        if used is None or total is None:
            return "Unavailable"
        return f"{used:.1f} / {total:.1f} GiB"

    cores = data.get("cpu_cores")
    usage = data.get("cpu_usage_percent")
    usage_text = f"{usage:.1f}%" if usage is not None else "Collecting / unavailable"
    ram_text = ratio(data.get('ram_used_gib'), data.get('ram_total_gib'))
    if data.get('ram_usage_percent') is not None:
        ram_text += f"  ·  {data['ram_usage_percent']:.1f}% usage"
    gpu = data.get("gpu_usage_percent")
    gpu_text = f"{gpu:.1f}% usage" if gpu is not None else "Unavailable"
    temperature = data.get("cpu_temperature_c")
    temperature_text = f"{temperature:.1f} °C" if temperature is not None else "Unavailable"
    return (
        f"CPU  /  {cores if cores is not None else 'Unavailable'} logical processors"
        f"  ·  {usage_text} usage\n"
        f"RAM  /  {ram_text}\n"
        f"DISK  /  {ratio(data.get('disk_used_gib'), data.get('disk_total_gib'))}\n"
        f"GPU  /  {gpu_text}\n"
        f"CPU TEMPERATURE  /  {temperature_text}\n"
        f"NETWORK  /  {data.get('network_status', 'Not measured')}"
    )
