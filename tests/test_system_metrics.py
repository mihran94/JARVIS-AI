"""Offline unit tests for the system counters and HUD formatter."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from desktop.system_metrics import CpuSampler, format_snapshot, snapshot


class DashboardTests(unittest.TestCase):
    def test_cpu_percentage_is_visible(self):
        display = format_snapshot({
            "cpu_cores": 8, "cpu_usage_percent": 23.5,
            "ram_used_gib": 4.0, "ram_total_gib": 16.0,
            "disk_used_gib": 80.0, "disk_total_gib": 200.0,
            "network_status": "Not measured",
        })
        self.assertIn("23.5% usage", display)
        self.assertIn("4.0 / 16.0 GiB", display)
        self.assertIn("Not measured", display)

    def test_missing_values_are_explicit(self):
        display = format_snapshot({})
        self.assertIn("Collecting / unavailable", display)
        self.assertIn("RAM  /  Unavailable", display)

    def test_first_cpu_read_sets_the_baseline(self):
        with patch("desktop.system_metrics.psutil.cpu_percent", side_effect=[0.0, 31.2]) as read:
            sampler = CpuSampler()
            self.assertIsNone(sampler.sample())
            self.assertEqual(sampler.sample(), 31.2)
            read.assert_called_with(interval=None)

    def test_ram_snapshot_uses_the_operating_system_percentage(self):
        gib = 1024 ** 3
        memory = SimpleNamespace(total=16 * gib, available=12 * gib, percent=25.0)
        with patch("desktop.system_metrics.psutil.virtual_memory", return_value=memory):
            data = snapshot()
        self.assertEqual(data['ram_usage_percent'], 25.0)
        self.assertIn('4.0 / 16.0 GiB  ·  25.0% usage', format_snapshot(data))


if __name__ == "__main__":
    unittest.main()
