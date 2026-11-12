# JARVIS BLUE MOBILE — Security Review

Date: 12 November 2026
Scope: the merged `AndroidManifest.xml`, the sensitive services, the consent
model and the distribution of the APK.

This file records what was audited, what was changed and what is still the
owner's part. It does not claim a certification.

---

## 1. What was audited

| Area | Finding |
|---|---|
| Manifest permissions | Every declared permission is used, and the two system services keep their binding permissions. |
| Backup | `allowBackup="false"` and the extraction rules exclude every domain, so nothing leaves the device through backup or device transfer. |
| Accessibility service | The screen reading was switched off completely, because there was no consent to check. |
| Notification listener | The content capture was switched off completely, for the same reason. |
| Microphone | The wake-word service and the system recognition entry point used the Android runtime permission alone. |
| Background work | The scheduled worker ran whenever it was scheduled. |
| Tool permissions | The in-app grant store was in place and used by the tool executor. |
| The grant store itself | Encrypted at rest, per bucket and per tool, revocable. |

The gap was not that the sensitive services were unsafe. It was that they
were **unreachable**: the capture was off with a hard-coded flag, so the user
had no way to allow it, and the flag was the only thing that decided.

## 2. What changed

The hard-coded flags are gone. Every sensitive capture now asks a consent
store that the user controls, and the check happens at the moment of the
capture.

| Capture | Bucket | Without the consent |
|---|---|---|
| `microphone.capture` | `microphone` | The wake-word service stops itself; the system recognition entry point refuses the request. |
| `accessibility.screen` | `accessibility` | Nothing is read, and the text that was read before is dropped. |
| `notifications.content` | `notifications.read` | Nothing is recorded at all, not even the package name. |
| `background.service` | `background.service` | The scheduled worker returns without doing anything. |

The switches are in *Permissions → Privacy*. The default is **denied** for
all four, on a fresh install and after "Revoke every in-app grant".

The rules live in two places:

- `core/model/SensitiveCapture.kt` — the capabilities and the consent value
  object. Pure Kotlin, no Android, so it can be tested on a plain JVM.
- `core/security/SensitiveCaptureConsent.kt` — the bridge between the
  encrypted grant store and the capabilities.

The audit trail is `scripts/check_sensitive_services.py`. It fails the build
when a capture path stops asking for the consent, when a hard-coded flag
comes back, when the manifest loses a binding permission, or when the consent
model stops denying by default. The guard was proved to have teeth: removing
one consent check makes it fail.

## 3. The Play Protect warning

This is expected and it is not a bug in the build. There are three separate
things, and only the third one needs an action.

**1. "This app was not made by a verified developer."** Every APK that is
installed from outside the Play Store shows this. It says that the publisher
is unknown, not that the app is harmful. The debug APK is signed with the
automatic debug key, which no device trusts.

**2. "This app can collect sensitive data."** The app declares an
accessibility service and a notification listener, and Play Protect points
out that these can read what is on the screen. The app is honest about it:
the accessibility service description in *Settings* says exactly what it does
and what it cannot do, and the system keeps its status-bar entry visible
while it runs.

**3. "This app may be unsafe" / the app is blocked.** This one is caused by
the release signing key. That key was published inside a shareable archive
together with its password, so it must be treated as public. Google can flag
a certificate that has been seen in the wild, and every APK signed with a
flagged certificate is blocked on the device. That is the correct behaviour
on Google's side and it is not something to work around.

The fix is the key rotation, which needs the owner because it needs the
keystore password and the release environment secrets:

1. generate a new upload key and a new app signing key,
2. keep the new key out of the repository,
3. publish the update with the new key,
4. and never sign anything with the exposed key again.

Play Protect is **not** disabled and must not be. The right way to deal with
the warning is to rotate the key and to distribute the build from a channel
that Play can attribute, not to turn the check off.

## 4. What was not changed

- The app still asks for the permissions it needs. Removing a permission
  would remove a feature rather than fix a security problem.
- The accessibility service still cannot perform gestures and still needs
  the system toggle as well as the in-app consent.
- The notification listener still records nothing without the consent, so the
  "summarise my notifications" feature needs the user to allow it once.

## 5. Still open for the owner

| Item | Why it needs the owner |
|---|---|
| Release key rotation | Needs the keystore password and the release secrets |
| Play Store track | Needs the owner account and the new signing key |
| Device test of the consent switches | Needs a physical device with Android 12 or newer |
| `adb` install of the debug build | The debug APK is signed with a key the device does not know, so the phone asks to allow the source |
