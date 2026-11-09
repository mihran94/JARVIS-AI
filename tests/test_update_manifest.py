"""Offline tests for the GitHub Releases update-feed generator."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_update_manifest.py"


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.apk = self.root / "release.apk"
        self.apk.write_bytes(b"APK-test-fixture-no-secrets" * 100)

    def run_generator(self, url="https://github.com/test/app/releases/download/v1/release.apk",
                      package="com.jarvisblue.mobile", version="2"):
        destination = self.root / "update.json"
        proc = subprocess.run([
            sys.executable, str(SCRIPT), "--apk", str(self.apk),
            "--apk-url", url, "--package-id", package, "--version-code", version,
            "--version-name", "1.1.7", "--output", str(destination)
        ], text=True, capture_output=True)
        return proc, destination

    def test_feed_has_required_fields_and_real_checksum(self):
        proc, output = self.run_generator()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        feed = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(feed["packageId"], "com.jarvisblue.mobile")
        self.assertEqual(feed["versionCode"], 2)
        self.assertEqual(feed["versionName"], "1.1.7")
        self.assertEqual(feed["sha256"], hashlib.sha256(self.apk.read_bytes()).hexdigest())
        self.assertTrue(feed["apkUrl"].startswith("https://"))

    def test_rejects_untrusted_or_malformed_urls(self):
        for url in (
            "http://example.com/release.apk", "https://name:password@example.com/release.apk",
            "https://example.com:8080/release.apk", "file:///tmp/release.apk",
        ):
            with self.subTest(url=url):
                proc, output = self.run_generator(url=url)
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse(output.exists())

    def test_rejects_invalid_package_and_version(self):
        for overrides in ({"package": "bad"}, {"version": "0"}, {"version": "-2"}):
            with self.subTest(**overrides):
                proc, output = self.run_generator(**overrides)
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse(output.exists())

    def test_rejects_tiny_archive(self):
        self.apk.write_bytes(b"not-an-apk")
        proc, output = self.run_generator()
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
