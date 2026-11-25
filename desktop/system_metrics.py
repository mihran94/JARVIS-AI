"""CPU, memory, disk and available thermal counters from the local system."""
from pathlib import Path
import os
import shutil

import psutil


class CpuSampler:
    def __init__(self):
        self.ready = False

    def sample(self):
        try:
            percent = psutil.cpu_percent(interval=None)
        except (OSError, RuntimeError, psutil.Error):
            self.ready = False
            return None
        previous_sample = self.ready
        self.ready = True
        return percent if previous_sample else None


def _gib(count):
    return round(count / 2**30, 1)


def cpu_temperature():
    query = getattr(psutil, 'sensors_temperatures', None)
    if query is None:
        return None
    try:
        groups = query()
    except (OSError, RuntimeError, psutil.Error):
        return None
    readings = [
        sensor.current for name, sensors in groups.items()
        if name.casefold() in {'coretemp', 'k10temp', 'cpu_thermal'}
        for sensor in sensors if sensor.current is not None
    ]
    return round(max(readings), 1) if readings else None


def snapshot(path=None, cpu_sampler=None):
    result = dict(
        cpu_cores=os.cpu_count(),
        cpu_usage_percent=cpu_sampler.sample() if cpu_sampler is not None else None,
        ram_usage_percent=None, ram_used_gib=None, ram_total_gib=None,
        disk_used_gib=None, disk_total_gib=None, network_status='Not measured',
        gpu_usage_percent=None, cpu_temperature_c=cpu_temperature(),
    )
    try:
        disk = shutil.disk_usage(Path(path) if path else Path.home())
        result.update(disk_used_gib=_gib(disk.used), disk_total_gib=_gib(disk.total))
    except (OSError, ValueError):
        pass
    try:
        memory = psutil.virtual_memory()
        result.update(ram_usage_percent=memory.percent,
                      ram_used_gib=_gib(memory.total - memory.available),
                      ram_total_gib=_gib(memory.total))
    except (OSError, RuntimeError, psutil.Error):
        pass
    return result


def format_snapshot(data):
    def ratio(prefix):
        used, total = data.get(prefix + '_used_gib'), data.get(prefix + '_total_gib')
        return 'Unavailable' if used is None or total is None else f'{used:.1f} / {total:.1f} GiB'

    def usage(key):
        value = data.get(key)
        return 'Unavailable' if value is None else f'{value:.1f}% usage'

    ram = ratio('ram')
    if data.get('ram_usage_percent') is not None:
        ram += '  ·  ' + usage('ram_usage_percent')
    temperature = data.get('cpu_temperature_c')
    thermal = 'Unavailable' if temperature is None else f'{temperature:.1f} °C'
    cpu_usage = 'Collecting / unavailable' if data.get('cpu_usage_percent') is None else usage('cpu_usage_percent')
    return '\n'.join((
        f"CPU  /  {data.get('cpu_cores') or 'Unavailable'} logical processors  ·  {cpu_usage}",
        f"RAM  /  {ram}",
        f"DISK  /  {ratio('disk')}",
        f"GPU  /  {usage('gpu_usage_percent')}",
        f"CPU TEMPERATURE  /  {thermal}",
        f"NETWORK  /  {data.get('network_status', 'Not measured')}",
    ))
