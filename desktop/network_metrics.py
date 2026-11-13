"""Read-only network throughput sampling for the local Windows dashboard.

psutil provides aggregate OS interface counters. No network connections are made.
"""
import time

try:
    import psutil
except ImportError:
    psutil = None


class NetworkSampler:
    def __init__(self, counter_reader=None, clock=None):
        self.counter_reader = counter_reader if counter_reader is not None else (
            (lambda: psutil.net_io_counters(nowrap=True)) if psutil else None
        )
        self.clock = clock or time.monotonic
        self.previous = None

    def sample(self):
        if self.counter_reader is None:
            return None
        try:
            counters = self.counter_reader()
            now = self.clock()
            if counters is None:
                self.previous = None
                return None
            current = (now, counters.bytes_sent, counters.bytes_recv)
        except (OSError, RuntimeError, AttributeError, ValueError, TypeError):
            self.previous = None
            return None
        previous = self.previous
        self.previous = current
        if previous is None:
            return None
        elapsed = now - previous[0]
        sent = current[1] - previous[1]
        received = current[2] - previous[2]
        if elapsed <= 0 or sent < 0 or received < 0:
            return None
        return (sent / elapsed / 1024, received / elapsed / 1024)


def format_network(rates):
    if rates is None:
        return "Collecting / unavailable"
    upload, download = rates
    return f"Upload {upload:.1f} KiB/s  ·  Download {download:.1f} KiB/s"
