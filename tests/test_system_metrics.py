"""Offline unit tests for the Windows dashboard formatter and CPU sampler."""
import unittest
from unittest.mock import patch
from desktop.system_metrics import CpuSampler, format_snapshot


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

    def test_non_windows_sampler_is_unavailable(self):
        with patch("desktop.system_metrics.sys.platform", "linux"):
            self.assertIsNone(CpuSampler().sample())


if __name__ == "__main__":
    unittest.main()
