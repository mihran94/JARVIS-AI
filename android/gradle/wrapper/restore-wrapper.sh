#!/usr/bin/env bash
# Restore the Gradle wrapper JAR from its base64 sidecar.
#
# Why this file exists:
#   This repository was published through an API that transports file contents as
#   UTF-8 text, so the binary gradle-wrapper.jar could not be committed as a
#   binary blob. The sidecar gradle-wrapper.jar.b64 holds the byte-exact
#   original (SHA-256 below); this script decodes it back into place.
#
#   SHA-256: 2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046
#
# Usage:  bash gradle/wrapper/restore-wrapper.sh
# After running it, ./gradlew works exactly as it did before.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sidecar="$here/gradle-wrapper.jar.b64"
target="$here/gradle-wrapper.jar"

if [ ! -f "$sidecar" ]; then
  echo "error: $sidecar not found" >&2
  exit 1
fi

if [ -f "$target" ] && [ "$(sha256sum "$target" | cut -d' ' -f1)" = "2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046" ]; then
  echo "gradle-wrapper.jar already present and intact"
  exit 0
fi

base64 --decode "$sidecar" > "$target"
echo "restored $target"
sha256sum "$target"
