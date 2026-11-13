#!/usr/bin/env python3
"""Fail-closed source guard for the remote-only Android launcher.

This build mode runs Windows JARVIS as the only AI/tool brain. Dormant legacy
Android sources may remain for code history, but none may be activated by the
app manifest or launcher. Checks run before compiling the debug APK.
"""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/src/main"
KOTLIN = APP / "kotlin/com/jarvisblue/mobile"
ANDROID = "{http://schemas.android.com/apk/res/android}"

ALLOWED_PERMISSIONS = {
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.USE_BIOMETRIC",
}


def check() -> list[str]:
    problems = []
    try:
        tree = ET.parse(APP / "AndroidManifest.xml")
        root = tree.getroot()
    except (OSError, ET.ParseError) as exc:
        return [f"Remote manifest is missing or invalid: {exc}"]
    app = root.find("application")
    if app is None:
        return ["Android remote must declare exactly one application"]
    if app.get(ANDROID + "allowBackup") != "false":
        problems.append("Remote pairing credentials must not enter Android backups")
    if app.get(ANDROID + "name") != ".JarvisApplication":
        problems.append("Remote-only application host is required")

    permissions = {node.get(ANDROID + "name")
                   for node in root.findall("uses-permission")}
    extra = permissions - ALLOWED_PERMISSIONS
    if extra:
        problems.append("Remote must not request standalone Android permissions: "
                        + ", ".join(sorted(extra)))
    if not {"android.permission.INTERNET"}.issubset(permissions):
        problems.append("Remote requires permission to connect to Windows")
    for name in ("service", "receiver"):
        if app.findall(name):
            problems.append(f"Remote manifest must not register any {name}s")
    activities = app.findall("activity")
    if len(activities) != 1 or activities[0].get(ANDROID + "name") != ".MainActivity":
        problems.append("Only the Windows remote MainActivity may be launched")
    for activity in activities:
        if activity.get(ANDROID + "exported") != "true":
            problems.append("The remote launcher must have a visible activity")
    providers = app.findall("provider")
    startup = [node for node in providers
               if node.get(ANDROID + "name") == "androidx.startup.InitializationProvider"]
    if len(startup) != 1 or not any(
        node.get(ANDROID + "name") == "androidx.work.WorkManagerInitializer"
        and node.get("{http://schemas.android.com/tools}node") == "remove"
        for node in startup[0].findall("meta-data")
    ):
        problems.append("Old standalone background jobs must not restart automatically")

    screens = (KOTLIN / "navigation/JarvisApp.kt").read_text(encoding="utf-8")
    host = (KOTLIN / "JarvisApplication.kt").read_text(encoding="utf-8")
    activity = (KOTLIN / "MainActivity.kt").read_text(encoding="utf-8")
    viewmodel = (ROOT / "feature/command/src/main/kotlin/com/jarvisblue/feature/command/WindowsViewModel.kt").read_text(encoding="utf-8")
    bridge = (ROOT / "core/windows/src/main/kotlin/com/jarvisblue/core/windows/BridgeClient.kt").read_text(encoding="utf-8")
    if "WindowsRoute()" not in screens or any(
        forbidden in screens
        for forbidden in ("AssistantRoute(", "ChatRoute(", "StudioRoute(", "TasksRoute(")
    ):
        problems.append("Main Android route must contain only the Windows remote")
    if "WorkManager.initialize(" in host or "registerTools(" in host:
        problems.append("Android remote must not start local agents or scheduled tasks")
    if "RECORD_AUDIO" in activity or "RequestPermission" in activity:
        problems.append("Remote-only app must never request phone microphone access")
    if "DesktopEndpoint.baseUrl(" not in viewmodel or '"http://' in viewmodel:
        problems.append("Windows pairing must use a strict HTTPS endpoint")
    if ('secureEndpoint(baseUrl)' not in bridge or
            'require(origin.scheme == "https"' not in bridge):
        problems.append("Every bridge request must enforce HTTPS")
    return problems


if __name__ == "__main__":
    failures = check()
    for problem in failures:
        print("FAIL:", problem, file=sys.stderr)
    if failures:
        sys.exit(1)
    print("PASS: Android exposes only an HTTPS Windows remote, with no local AI tools or capture permissions")
