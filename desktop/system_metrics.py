"""Read local OS counters for the desktop HUD without opening network connections."""
import os
from pathlib import Path
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
    return (
        f"CPU  /  {cores if cores is not None else 'Unavailable'} logical processors"
        f"  ·  {usage_text} usage\n"
        f"RAM  /  {ram_text}\n"
        f"DISK  /  {ratio(data.get('disk_used_gib'), data.get('disk_total_gib'))}\n"
        f"NETWORK  /  {data.get('network_status', 'Not measured')}"
    )
