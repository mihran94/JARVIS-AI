"""Offline regression tests for passive network throughput calculation."""
from types import SimpleNamespace
import unittest

from desktop.network_metrics import NetworkSampler, format_network


class NetworkMetricsTests(unittest.TestCase):
    def test_rates_from_counter_deltas(self):
        values = iter([
            SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
            SimpleNamespace(bytes_sent=3048, bytes_recv=6096),
        ])
        ticks = iter([10.0, 12.0])
        sampler = NetworkSampler(counter_reader=lambda: next(values), clock=lambda: next(ticks))
        self.assertIsNone(sampler.sample())
        self.assertEqual(sampler.sample(), (1.0, 2.0))
        self.assertIn("Upload 1.0 KiB/s", format_network((1.0, 2.0)))

    def test_counter_reset_returns_unavailable(self):
        values = iter([
            SimpleNamespace(bytes_sent=500, bytes_recv=500),
            SimpleNamespace(bytes_sent=100, bytes_recv=100),
        ])
        ticks = iter([1.0, 2.0])
        sampler = NetworkSampler(counter_reader=lambda: next(values), clock=lambda: next(ticks))
        self.assertIsNone(sampler.sample())
        self.assertIsNone(sampler.sample())

    def test_missing_counter_reader(self):
        sampler = NetworkSampler(counter_reader=lambda: None)
        self.assertIsNone(sampler.sample())
        self.assertIn("unavailable", format_network(None))


if __name__ == "__main__":
    unittest.main()
