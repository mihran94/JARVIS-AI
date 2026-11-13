"""Android is a phone remote for the owner-controlled Windows JARVIS.

This source-level test runs without Android SDK; the APK's merged manifest
and phone hardware still require separate acceptance testing.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "android/scripts/check_sensitive_services.py"


def test_remote_only_manifest_and_launcher_guard_pass():
    proc = subprocess.run([sys.executable, str(SCRIPT)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "remote" in proc.stdout.lower()


def test_mobile_has_no_trading_or_separate_assistant_entrypoint():
    app = (ROOT / "android/app/src/main/kotlin/com/jarvisblue/mobile/navigation/JarvisApp.kt").read_text(encoding="utf-8")
    assert "WindowsRoute()" in app
    for forbidden in ("GoldMarketRoute(", "AssistantRoute(", "ChatRoute(",
                      "StudioRoute(", "Exness", "XAUUSD"):
        assert forbidden not in app
