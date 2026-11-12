"""Live numbers for the device dashboard.

The bridge status call reports what the PC is doing, and the phone shows it.
The numbers are read with the standard library only, so the pinned
dependencies stay as they are and nothing new has to be installed on the
owner's machine.

What is available depends on the system:

- the disk figures work everywhere;
- the memory figure works on Windows, Linux and macOS;
- the CPU figure works on Windows and Linux, and stays empty elsewhere;
- the GPU figure needs a vendor tool, so it stays empty and is reported as
  unknown rather than guessed.
"""
import os
import platform
import shutil
import time

#: How often the CPU times are sampled, in seconds. The first call needs two
#: samples, so the first reading is empty.
CPU_SAMPLE_SECONDS = 0.25


class PlatformMetrics:
    """Reads the machine state for the status call."""

    def __init__(self, *, root: str | None = None, now=time.time):
        self._root = root or (os.path.abspath(os.sep))
        self._now = now
        self._cpu_previous = None
        self._started = now()

    # ----------------------------------------------------------------- public

    def snapshot(self) -> dict:
        """The numbers that are known right now."""
        return {
            'cpu_percent': self.cpu_percent(),
            'memory_percent': self.memory_percent(),
            'gpu_percent': None,
            'disk_free_gb': self.disk_free_gb(),
            'disk_total_gb': self.disk_total_gb(),
            'uptime_seconds': self.uptime_seconds(),
        }

    def uptime_seconds(self) -> int:
        """How long the desktop has been running."""
        return max(0, int(self._now() - self._started))

    def disk_free_gb(self) -> float | None:
        """Free space on the system drive, in gigabytes."""
        try:
            usage = shutil.disk_usage(self._root)
        except OSError:
            return None
        return round(usage.free / (1024 ** 3), 2)

    def disk_total_gb(self) -> float | None:
        """Total space on the system drive, in gigabytes."""
        try:
            usage = shutil.disk_usage(self._root)
        except OSError:
            return None
        return round(usage.total / (1024 ** 3), 2)

    def memory_percent(self) -> float | None:
        """How much of the memory is in use, as a percentage."""
        system = platform.system()
        if system == 'Windows':
            return self._windows_memory()
        if system == 'Linux':
            return self._linux_memory()
        if system == 'Darwin':
            return self._darwin_memory()
        return None

    def cpu_percent(self) -> float | None:
        """How busy the processor is, as a percentage.

        The first call returns None, because one sample is not a rate.
        """
        system = platform.system()
        if system == 'Windows':
            return self._windows_cpu()
        if system == 'Linux':
            return self._linux_cpu()
        return None

    # ----------------------------------------------------------------- Windows

    def _windows_memory(self) -> float | None:
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('memory_load', ctypes.c_ulong),
                            ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                            ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                            ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                            ('avail_ext', ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
        except (AttributeError, OSError, ValueError):
            return None
        return round(float(status.memory_load), 1)

    def _windows_cpu(self) -> float | None:
        try:
            import ctypes

            class FileTime(ctypes.Structure):
                _fields_ = [('low', ctypes.c_ulong), ('high', ctypes.c_ulong)]

            def read(handle_id):
                handle = ctypes.windll.kernel32.GetSystemTimeAsFileTime
                filetime = FileTime()
                handle(ctypes.byref(filetime))
                return (filetime.high << 32) | filetime.low

            idle = read(0)
            kernel = read(1)
            user = read(2)
        except (AttributeError, OSError, ValueError):
            return None
        current = (idle, kernel, user)
        previous = self._cpu_previous
        self._cpu_previous = current
        if previous is None:
            return None
        idle_delta = current[0] - previous[0]
        kernel_delta = current[1] - previous[1]
        user_delta = current[2] - previous[2]
        total = kernel_delta + user_delta
        if total <= 0:
            return None
        busy = total - idle_delta
        return round(max(0.0, min(100.0, busy * 100.0 / total)), 1)

    # ------------------------------------------------------------------ Linux

    def _linux_memory(self) -> float | None:
        try:
            with open('/proc/meminfo', encoding='utf-8') as handle:
                values = {}
                for line in handle:
                    key, _, rest = line.partition(':')
                    values[key.strip()] = float(rest.strip().split()[0])
        except (OSError, IndexError, ValueError):
            return None
        total = values.get('MemTotal')
        available = values.get('MemAvailable')
        if not total:
            return None
        if available is None:
            available = values.get('MemFree', 0) + values.get('Cached', 0)
        used = total - available
        return round(max(0.0, min(100.0, used * 100.0 / total)), 1)

    def _linux_cpu(self) -> float | None:
        try:
            with open('/proc/stat', encoding='utf-8') as handle:
                for line in handle:
                    if line.startswith('cpu '):
                        parts = [float(value) for value in line.split()[1:]]
                        break
                else:
                    return None
        except (OSError, IndexError, ValueError):
            return None
        total = sum(parts)
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)
        previous = self._cpu_previous
        self._cpu_previous = (total, idle)
        if previous is None:
            return None
        total_delta = total - previous[0]
        idle_delta = idle - previous[1]
        if total_delta <= 0:
            return None
        return round(max(0.0, min(100.0, (total_delta - idle_delta) * 100.0 / total_delta)), 1)

    # ----------------------------------------------------------------- macOS

    def _darwin_memory(self) -> float | None:
        try:
            total = self._sysctl('hw.memsize')
            page_size = 4096
            free_pages = self._sysctl('vm.page_free_count')
            inactive = self._sysctl('vm.page_inactive_count')
        except (OSError, ValueError, TypeError):
            return None
        if not total:
            return None
        used = total - (free_pages + inactive) * page_size
        return round(max(0.0, min(100.0, used * 100.0 / total)), 1)

    @staticmethod
    def _sysctl(name: str):
        import subprocess
        completed = subprocess.run(['sysctl', '-n', name], capture_output=True, text=True,
                                   timeout=5)
        if completed.returncode != 0:
            raise OSError('sysctl failed')
        return int(completed.stdout.strip())
