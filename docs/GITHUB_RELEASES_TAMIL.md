# JARVIS BLUE Mobile: GitHub Releases / In-App Updates

## Repositories
- Private Android source: https://github.com/mihran94/jarvis-blue-android
- Public APK distribution: https://github.com/mihran94/JARVIS-Mobile-Beta
- Stable update-feed URL (only after first release):
  https://raw.githubusercontent.com/mihran94/JARVIS-Mobile-Beta/main/update.json

The phone app accepts the feed under **Settings > App updates & about**. APK updates must match package ID, signing certificate, and an increased versionCode. Android requires installation confirmation; Play Protect is never bypassed.

## STATUS / blocker
The source on GitHub is currently **v1.0.0**, while the newer ZIP is **v1.1.7**. First securely sync and test v1.1.7 source to the private repository. The workflow refuses to publish when input versionName differs from GitHub source. No APK release or update.json has been published by this setup.

## GitHub private source repository settings

Open https://github.com/mihran94/jarvis-blue-android/settings/secrets/actions and configure these secrets:
- `JARVIS_RELEASE_KEYSTORE_BASE64`: base64 of the SAME original release-signing .p12 keystore. Do NOT use an arbitrary new key for installed release-app updates.
- `JARVIS_RELEASE_STORE_PASSWORD`
- `JARVIS_RELEASE_KEY_ALIAS`
- `JARVIS_RELEASE_KEY_PASSWORD`
- `JARVIS_BETA_RELEASE_TOKEN`: fine-grained GitHub PAT restricted to **JARVIS-Mobile-Beta** ONLY, with **Contents: Read and write**. Set an expiration.

Open https://github.com/mihran94/jarvis-blue-android/settings/variables/actions and add:
- `JARVIS_RELEASE_CERT_SHA256`: expected SHA-256 certificate fingerprint of the original installed RELEASE APK (not the APK checksum). The previously verified original release APK showed `44cb295eb9e11dccd6bef68145290f3ea86d278ef14a207da60ed39509f474a7`; verify against your actual installed release before relying on it.

Recommended: create GitHub Actions environment `android-release` with required reviewer approval, so manual release requires a second confirmation.

## Run only when ready

1. Verify source code is up to date and tests/build pass; review permissions and any Play Protect warnings.
2. Set versionCode larger than all installed release builds and versionName matching your tag, e.g. 1.1.7.
3. Open https://github.com/mihran94/jarvis-blue-android/actions/workflows/android-release.yml and choose **Run workflow**.
4. Enter matching version_name and notes; explicitly check confirm_public_release.
5. The workflow builds a release APK with the protected keystore, verifies the certificate/package/version, publishes a release APK to public **JARVIS-Mobile-Beta**, then writes update.json there.
6. In the RELEASE Android app, configure Settings > App updates with:
   https://raw.githubusercontent.com/mihran94/JARVIS-Mobile-Beta/main/update.json

Debug builds (`com.jarvisblue.mobile.debug`) CANNOT update from this release feed (`com.jarvisblue.mobile`). Debug APKs signed with a different debug certificate cannot be installed over existing builds with a different certificate. Keep the original app installed and back up important data.

## Security
- Do not commit `keystore/*.p12`, `keystore/keystore.properties`, API keys, Python .env files, broker credentials, or release passwords.
- The publicly released APK is accessible to anyone; inspect the manifest and security permissions before publishing.
- Exness Ed25519 private key stays in a private Windows bridge. It is NEVER part of the Android APK.
- The updater verifies APK SHA-256 and installed signer and requires Android installer user confirmation.
- This workflow NEVER auto-runs on push and NEVER publishes without manual confirmation and configured credentials.
