"""Read-only local system snapshot using Python's standard library.

No network requests, background subprocesses, credentials, or elevated privileges.
"""
import ctypes
import os
from pathlib import Path
import shutil
import sys


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


def snapshot(path=None):
    """Return basic metrics or explicit unavailable values; never guess CPU load."""
    root = Path(path or Path.home())
    data = {
        "cpu_cores": os.cpu_count(),
        "cpu_usage_percent": None,
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
