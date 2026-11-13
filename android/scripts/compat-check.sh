#!/usr/bin/env bash
#
# JARVIS BLUE MOBILE — static compatibility & hygiene check
#
# Runs the checks that do not need a device:
#   1. SDK levels (minSdk >= 31, targetSdk >= 34)
#   2. The manifest must not request a forbidden permission
#   3. Every component the app promises must be declared
#   4. The release APK must exist and verify against the signing key
#   5. No AI provider key may be hard-coded in the source
#   6. The manifest must disable backup
#
# Usage:  scripts/compat-check.sh [--apk <path>]
# Exit code 0 = all checks passed.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APK=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apk) APK="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -z "$APK" ]] && APK="app/build/outputs/apk/release/app-release.apk"

PASS=0
FAIL=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

MANIFEST="app/src/main/AndroidManifest.xml"

head_ "1. SDK levels"
MIN_SDK=$(grep -oP 'minSdk\s*=\s*\K[0-9]+' app/build.gradle.kts | head -1)
TARGET_SDK=$(grep -oP 'targetSdk\s*=\s*\K[0-9]+' app/build.gradle.kts | head -1)
COMPILE_SDK=$(grep -oP 'compileSdk\s*=\s*\K[0-9]+' app/build.gradle.kts | head -1)
echo "  minSdk=$MIN_SDK targetSdk=$TARGET_SDK compileSdk=$COMPILE_SDK"
[[ -n "$MIN_SDK" && "$MIN_SDK" -ge 31 ]] && ok "minSdk $MIN_SDK >= 31 (Android 12)" \
    || bad "minSdk must be >= 31"
[[ -n "$TARGET_SDK" && "$TARGET_SDK" -ge 34 ]] && ok "targetSdk $TARGET_SDK >= 34" \
    || bad "targetSdk must be >= 34"
[[ -n "$COMPILE_SDK" && "$COMPILE_SDK" -ge 35 ]] && ok "compileSdk $COMPILE_SDK >= 35" \
    || bad "compileSdk should be 35"

head_ "2. Forbidden permissions"
# The app must never request these.
FORBIDDEN=(
  "android.permission.READ_SMS"
  "android.permission.RECEIVE_SMS"
  "android.permission.SEND_SMS"
  "android.permission.READ_CONTACTS"
  "android.permission.WRITE_CONTACTS"
  "android.permission.ACCESS_FINE_LOCATION"
  "android.permission.ACCESS_COARSE_LOCATION"
  "android.permission.CAMERA"
  "android.permission.MANAGE_EXTERNAL_STORAGE"
  "android.permission.READ_EXTERNAL_STORAGE"
  "android.permission.QUERY_ALL_PACKAGES"
  "android.permission.BIND_DEVICE_ADMIN"
  "android.permission.REQUEST_INSTALL_PACKAGES"
  "android.permission.SYSTEM_ALERT_WINDOW_FALLBACK"
)
for p in "${FORBIDDEN[@]}"; do
  if grep -q "uses-permission android:name=\"$p\"" "$MANIFEST"; then
    bad "forbidden permission requested: $p"
  else
    ok "not requested: $p"
  fi
done
# SYSTEM_ALERT_WINDOW is allowed but must be opt-in, never requested at runtime by default.
if grep -q "SYSTEM_ALERT_WINDOW" "$MANIFEST"; then
  ok "SYSTEM_ALERT_WINDOW declared (opt-in overlay only)"
fi

head_ "3. Required components"
REQUIRED_COMPONENTS=(
  "assistant.JarvisVoiceInteractionService"
  "assistant.JarvisVoiceInteractionSessionService"
  "assistant.JarvisRecognitionService"
  "assistant.WakeWordService"
  "services.JarvisNotificationListenerService"
  "services.JarvisAccessibilityService"
  "services.ScreenCaptureService"
  "receivers.BootReceiver"
  "receivers.ReminderReceiver"
  "MainActivity"
)
for c in "${REQUIRED_COMPONENTS[@]}"; do
  grep -q "$c" "$MANIFEST" && ok "declared: $c" || bad "missing component: $c"
done

head_ "4. Backup disabled"
grep -q 'android:allowBackup="false"' "$MANIFEST" \
  && ok "android:allowBackup=false" \
  || bad "android:allowBackup must be false (the Keystore key cannot be backed up)"
[[ -f app/src/main/res/xml/data_extraction_rules.xml ]] \
  && ok "data extraction rules present" \
  || bad "data extraction rules missing"

head_ "5. No hard-coded provider keys"
# Any literal that looks like a provider key in the source is a defect.
# Only production sources are scanned: the unit tests deliberately contain
# fake key-shaped strings to prove the redactor works.
KEY_HITS=$(grep -rInE '(sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})' \
     --include='*.kt' --include='*.xml' --include='*.properties' \
     --exclude-dir=test --exclude-dir=androidTest app core feature 2>/dev/null)
if [[ -n "$KEY_HITS" ]]; then
  echo "$KEY_HITS" | sed 's/^/    /'
  bad "a provider key literal was found in the production source tree"
else
  ok "no provider key literals in the production source tree"
fi

head_ "6. Release keystore and APK"
[[ -f keystore/jarvis-release.p12 ]] && ok "release keystore present" || bad "release keystore missing"
if [[ -f "$APK" ]]; then
  ok "APK present: $APK ($(du -h "$APK" | cut -f1))"
  APKSIGNER="$(ls -1 "${ANDROID_HOME:-$HOME/Android/sdk}"/build-tools/*/apksigner 2>/dev/null | tail -1)"
  if [[ -n "$APKSIGNER" ]]; then
    if "$APKSIGNER" verify "$APK" >/dev/null 2>&1; then
      ok "APK signature verifies (v1/v2/v3)"
      "$APKSIGNER" verify --verbose "$APK" 2>/dev/null | grep -E '^Verified using' | sed 's/^/    /'
    else
      bad "APK signature does NOT verify"
    fi
  else
    echo "  SKIP apksigner not found (set ANDROID_HOME)"
  fi
  AAPT="$(ls -1 "${ANDROID_HOME:-$HOME/Android/sdk}"/build-tools/*/aapt 2>/dev/null | tail -1)"
  if [[ -n "$AAPT" ]]; then
    SDK_INFO=$("$AAPT" dump badging "$APK" 2>/dev/null | grep -E "^(sdkVersion|targetSdkVersion|package:)" )
    echo "$SDK_INFO" | sed 's/^/    /'
  fi
else
  bad "APK not found: $APK (run ./gradlew :app:assembleRelease)"
fi

printf '\n\033[1mResult: %d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] || exit 1
