#!/usr/bin/env python3
"""Fail-closed source audit for sensitive Android listeners.

Run: python3 scripts/check_sensitive_services.py
This static guard is not a substitute for merged-manifest, APK or device tests.
"""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/src/main"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def check() -> list[str]:
    failures = []
    manifest = ET.parse(APP / "AndroidManifest.xml").getroot()
    app = manifest.find("application")
    if app is None:
        return ["AndroidManifest.xml has no application element"]
    if app.get(ANDROID + "allowBackup") != "false":
        failures.append("Android backups must remain disabled for sensitive assistant data")
    required = {
        ".services.JarvisAccessibilityService": "android.permission.BIND_ACCESSIBILITY_SERVICE",
        ".services.JarvisNotificationListenerService": "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
    }
    for service_name, permission in required.items():
        matches = [s for s in app.findall("service") if s.get(ANDROID + "name") == service_name]
        if len(matches) != 1 or matches[0].get(ANDROID + "permission") != permission:
            failures.append(f"{service_name}: missing system binding permission")
    sources = {
        "services/JarvisAccessibilityService.kt": (
            "private const val SCREEN_READING_ENABLED = false",
            "if (!SCREEN_READING_ENABLED) return",
        ),
        "services/JarvisNotificationListenerService.kt": (
            "private val notificationCaptureEnabled = false",
            "if (!notificationCaptureEnabled) return",
        ),
    }
    for filename, (off, guard) in sources.items():
        source = (APP / "kotlin/com/jarvisblue/mobile" / filename).read_text(encoding="utf-8")
        if off not in source or guard not in source:
            failures.append(f"{filename}: sensitive capture must remain disabled until consent is implemented")
    return failures


if __name__ == "__main__":
    errors = check()
    for error in errors:
        print("FAIL:", error, file=sys.stderr)
    if errors:
        sys.exit(1)
    print("PASS: sensitive listeners fail closed and require system-bound permissions")
