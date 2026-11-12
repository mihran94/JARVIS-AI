# Android release signing key: exposure, current state and rotation

## What happened

The keystore that signed the delivered JARVIS BLUE APKs was shipped inside a
shareable project archive together with its plaintext password. That archive
was handed out, so the key must be treated as **public**. Anyone holding it
can sign an update for the application id `com.jarvisblue.mobile`, which is
enough to replace an installed app on a device that trusts it.

The key was never committed to a Git repository. The `.gitignore` of
`mihran94/jarvis-blue-android` excludes `*.keystore`, `*.p12`, `*.jks` and
`keystore/`, and an earlier entry that un-ignored
`keystore/jarvis-release.p12` was removed.

## Current state, verified

Checked on 12 November 2026 across every branch of the four repositories:

| Repository | Branches | Signing material found |
| --- | --- | --- |
| `mihran94/JARVIS-AI` | 8 | none |
| `mihran94/jarvis-blue-android` | 4 | none |
| `mihran94/Jarvis-Blue` | 6 | none |
| `mihran94/JARVIS-Mobile-Beta` | 1 | none |

Only source files whose *name* mentions a keystore were found, such as
`core/security/.../KeystoreKeyManager.kt` and `SecretVault.kt`. Those are
code, not keys.

Two guards already exist in `jarvis-blue-android`:

- `.github/workflows/release-preflight.yml` asserts that no signing file and
  no credential file is tracked by git, on every pull request that touches the
  workflow, the manifest script or its test.
- `.github/workflows/android-release.yml` verifies the built APK with
  `apksigner` and refuses to publish when the certificate digest differs from
  `vars.JARVIS_RELEASE_CERT_SHA256`. A replaced key therefore cannot be
  published silently.

This repository also ships `scripts/check_signing_material.py`, which walks a
tree and reports any file that looks like a private key or a credential dump.
Run it before committing:

```
python scripts/check_signing_material.py .
```

## Rotation procedure

Rotating is the only way to make the old key worthless. The steps are the
owner's to run, because they need the keystore password and the release
environment secrets.

### 1. Create the new keystore

On the owner's Windows machine, with the Android SDK build tools installed:

```
keytool -genkeypair -v \
  -keystore %USERPROFILE%\.android\jarvis-release-v2.p12 \
  -alias jarvisblue -keyalg RSA -keysize 4096 -validity 10000
```

Use a new password. Do not reuse the old one, and do not store the password
next to the keystore.

### 2. Record the new certificate digest

```
keytool -list -v -keystore %USERPROFILE%\.android\jarvis-release-v2.p12
```

Copy the `SHA256` fingerprint. That value becomes the new
`JARVIS_RELEASE_CERT_SHA256` repository variable.

### 3. Update the release environment

In `mihran94/jarvis-blue-android`:

- Settings → Environments → `android-release` → update
  `JARVIS_RELEASE_KEYSTORE_BASE64` with the base64 of the new keystore:

  ```
  certutil -encode -f %USERPROFILE%\.android\jarvis-release-v2.p12 keystore.b64
  ```

- update `JARVIS_RELEASE_STORE_PASSWORD`, `JARVIS_RELEASE_KEY_ALIAS` and
  `JARVIS_RELEASE_KEY_PASSWORD` for the new key;
- update the repository variable `JARVIS_RELEASE_CERT_SHA256` to the new
  fingerprint.

### 4. Publish the first release with the new key

Dispatch the `JARVIS BLUE - Publish Android update` workflow manually, with
`confirm_public_release` set. The workflow stops with

```
STOP: APK certificate differs from original installed release
```

when the certificate does not match the variable, so update the variable
**before** the first run with the new key.

### 5. Install over the old build

A new signing key cannot update the existing installed app. The old app has
to be removed first:

```
adb uninstall com.jarvisblue.mobile
adb install app/build/outputs/apk/release/app-release.apk
```

The database and the encrypted secret vault live in the app's private storage,
so uninstalling removes them. Export anything that matters before the
uninstall, or accept the loss.

### 6. Retire the old key

After the new release is installed on the owner's device, delete the old
keystore file and remove the old secrets from the environment. Keep the old
key offline only if a rollback to the previous build is still wanted, and
destroy it once the rollback window closes.

## What is not covered

This document does not claim that the old key has been rotated. It has not
been, because the keystore password and the release environment are the
owner's. Until step 3 is done, the old key can still sign an update for
`com.jarvisblue.mobile`.
