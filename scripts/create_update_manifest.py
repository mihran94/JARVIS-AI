#!/usr/bin/env python3
"""Generate a JARVIS in-app update feed for a verified, signed APK.

This creates JSON locally. It never uploads APKs, keys, or credentials.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def generate(apk: Path, apk_url: str, package_id: str, version_code: int,
             version_name: str, notes: str) -> dict:
    if not apk.is_file() or apk.suffix.lower() != ".apk":
        raise ValueError("APK file missing or path does not end in .apk")
    url = urlsplit(apk_url)
    if (url.scheme != "https" or not url.hostname or url.username
            or url.password or url.port not in (None, 443) or url.fragment):
        raise ValueError("APK URL must use HTTPS, no credentials, custom port, or fragment")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package_id):
        raise ValueError("Invalid Android package identifier")
    if version_code < 1 or not version_name.strip():
        raise ValueError("Invalid version")
    digest = hashlib.sha256()
    with apk.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if apk.stat().st_size < 1024:
        raise ValueError("APK is suspiciously small")
    return {
        "packageId": package_id,
        "versionCode": version_code,
        "versionName": version_name.strip(),
        "apkUrl": apk_url,
        "sha256": digest.hexdigest(),
        "notes": notes[:2000],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Android OTA update.json")
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--apk-url", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--version-code", type=int, required=True)
    parser.add_argument("--version-name", required=True)
    parser.add_argument("--notes", default="Bug fixes and improvements")
    parser.add_argument("--output", type=Path, default=Path("update.json"))
    args = parser.parse_args()
    try:
        record = generate(args.apk, args.apk_url, args.package_id,
                          args.version_code, args.version_name, args.notes)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {args.output}; sha256={record['sha256']}")
    print("Before publishing: verify package, version and signing certificate with aapt2/apksigner.")


if __name__ == "__main__":
    main()
