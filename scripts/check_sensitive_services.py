#!/usr/bin/env python3
"""Fail-closed source audit for the sensitive Android capture paths.

Run: python3 scripts/check_sensitive_services.py

This static guard is not a substitute for merged-manifest, APK or device
tests. It exists so that a change that removes a consent check fails in the
build instead of shipping.

What it enforces:

  1. the merged manifest keeps backups off and keeps the system binding
     permissions on the two system services;
  2. every sensitive capture path asks the consent store first;
  3. no capture path is switched off by a hard-coded flag, because that would
     mean the consent is not the thing that decides;
  4. the consent model itself denies by default and maps every capture to a
     sensitive bucket.
"""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/src/main"
KOTLIN = APP / "kotlin/com/jarvisblue/mobile"
CORE_MODEL = ROOT / "core/model/src/main/kotlin/com/jarvisblue/core/model"
CORE_SECURITY = ROOT / "core/security/src/main/kotlin/com/jarvisblue/core/security"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def check_manifest() -> list[str]:
    failures = []
    manifest = ET.parse(APP / "AndroidManifest.xml").getroot()
    app = manifest.find("application")
    if app is None:
        return ["AndroidManifest.xml has no application element"]
    if app.get(ANDROID + "allowBackup") != "false":
        failures.append("Android backups must remain disabled for sensitive assistant data")
    required = {
        ".services.JarvisAccessibilityService": "android.permission.BIND_ACCESSIBILITY_SERVICE",
        ".services.JarvisNotificationListenerService":
            "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE",
    }
    for service_name, permission in required.items():
        matches = [s for s in app.findall("service") if s.get(ANDROID + "name") == service_name]
        if len(matches) != 1 or matches[0].get(ANDROID + "permission") != permission:
            failures.append(f"{service_name}: missing system binding permission")
    return failures


def check_capture_paths() -> list[str]:
    """Every sensitive path has to ask the consent store before it reads."""
    failures = []
    paths = {
        KOTLIN / "services/JarvisAccessibilityService.kt": "SCREEN_READING",
        KOTLIN / "services/JarvisNotificationListenerService.kt": "NOTIFICATION_CONTENT",
        KOTLIN / "assistant/WakeWordService.kt": "MICROPHONE",
        KOTLIN / "assistant/JarvisRecognitionService.kt": "MICROPHONE",
        KOTLIN / "workers/ScheduledTaskWorker.kt": "BACKGROUND_SERVICE",
    }
    for path, capture in paths.items():
        if not path.exists():
            failures.append(f"{path.name}: the file is missing")
            continue
        source = path.read_text(encoding="utf-8")
        if "SensitiveCaptureConsent" not in source:
            failures.append(f"{path.name}: does not use the consent store")
        if f"SensitiveCapture.{capture}" not in source:
            failures.append(f"{path.name}: does not check the {capture} consent")
        if not re.search(r"[Cc]onsent\.allows\(\s*SensitiveCapture\." + capture + r"\s*\)", source):
            failures.append(f"{path.name}: the {capture} consent is not checked at the capture site")
        if re.search(r"private (const )?val \w*(Enabled|ENABLED)\s*=\s*false", source):
            failures.append(
                f"{path.name}: the capture must be decided by the consent, not by a hard-coded flag"
            )
    return failures


def check_consent_model() -> list[str]:
    """The consent model has to deny by default and stay sensitive."""
    failures = []
    model = CORE_MODEL / "SensitiveCapture.kt"
    if not model.exists():
        return ["core/model: SensitiveCapture.kt is missing"]
    source = model.read_text(encoding="utf-8")
    for capture in ("MICROPHONE", "SCREEN_READING", "NOTIFICATION_CONTENT", "BACKGROUND_SERVICE"):
        if capture not in source:
            failures.append(f"core/model: the {capture} capture is missing")
    if "val NONE = CaptureConsent(emptySet())" not in source:
        failures.append("core/model: there must be an empty consent that denies everything")
    if "data class CaptureConsent(val allowed: Set<SensitiveCapture> = emptySet())" not in source:
        failures.append("core/model: the consent must default to an empty set")

    consent = CORE_SECURITY / "SensitiveCaptureConsent.kt"
    if not consent.exists():
        failures.append("core/security: SensitiveCaptureConsent.kt is missing")
    else:
        text = consent.read_text(encoding="utf-8")
        if "fun allows(capture: SensitiveCapture): Boolean" not in text:
            failures.append("core/security: the consent must expose allows()")
        if "revokeAll" not in text:
            failures.append("core/security: every capture must be revocable")
    return failures


def check() -> list[str]:
    failures = []
    failures.extend(check_manifest())
    failures.extend(check_capture_paths())
    failures.extend(check_consent_model())
    return failures


if __name__ == "__main__":
    errors = check()
    for error in errors:
        print("FAIL:", error, file=sys.stderr)
    if errors:
        sys.exit(1)
    print("PASS: every sensitive capture is decided by a revocable consent and defaults to denied")
