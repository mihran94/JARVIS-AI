"""Read-only local system snapshot using Python's standard library.

No network requests, background subprocesses, credentials, or elevated privileges.
"""
import ctypes
import os
from pathlib import Path
import shutil
import sys


class FILETIME(ctypes.Structure):
    _fields_ = [('dwLowDateTime', ctypes.c_ulong), ('dwHighDateTime', ctypes.c_ulong)]


def _filetime_value(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class CpuSampler:
    """Non-blocking Windows CPU usage sampler based on GetSystemTimes deltas."""
    def __init__(self):
        self.previous = None

    def sample(self):
        if sys.platform != 'win32':
            return None
        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        try:
            success = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        except (AttributeError, OSError):
            return None
        if not success:
            return None
        current = (_filetime_value(idle), _filetime_value(kernel), _filetime_value(user))
        previous = self.previous
        self.previous = current
        if previous is None:
            return None
        idle_delta = current[0] - previous[0]
        total_delta = current[1] + current[2] - previous[1] - previous[2]
        if total_delta <= 0 or idle_delta < 0:
            return None
        return round(max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))), 1)


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _gib(value):
    return round(value / (1024 ** 3), 1)


def snapshot(path=None, cpu_sampler=None):
    """Return basic metrics or explicit unavailable values; never guess CPU load."""
    root = Path(path or Path.home())
    data = {
        "cpu_cores": os.cpu_count(),
        "cpu_usage_percent": cpu_sampler.sample() if cpu_sampler is not None else None,
        "ram_used_gib": None,
        "ram_total_gib": None,
        "disk_used_gib": None,
        "disk_total_gib": None,
        "network_status": "Not measured",
    }
    try:
        usage = shutil.disk_usage(root)
        data["disk_used_gib"] = _gib(usage.used)
        data["disk_total_gib"] = _gib(usage.total)
    except (OSError, ValueError):
        pass
    if sys.platform == "win32":
        try:
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                data["ram_used_gib"] = _gib(status.ullTotalPhys - status.ullAvailPhys)
                data["ram_total_gib"] = _gib(status.ullTotalPhys)
        except (AttributeError, OSError, ValueError):
            pass
    return data


def format_snapshot(data):
    def ratio(used, total):
        if used is None or total is None:
            return "Unavailable"
        return f"{used:.1f} / {total:.1f} GiB"

    cores = data.get("cpu_cores")
    return (
        f"CPU  /  {cores if cores is not None else 'Unavailable'} logical processors"
        "  ·  usage not measured\n"
        f"RAM  /  {ratio(data.get('ram_used_gib'), data.get('ram_total_gib'))}\n"
        f"DISK  /  {ratio(data.get('disk_used_gib'), data.get('disk_total_gib'))}\n"
        f"NETWORK  /  {data.get('network_status', 'Not measured')}"
    )
