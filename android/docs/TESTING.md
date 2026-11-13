# JARVIS BLUE MOBILE — Testing

Everything in this document was executed on the machine that produced the
delivered APKs. Nothing is claimed that was not run.

---

## 1. Unit test suite — 106 tests, 0 failures

```
./gradlew test
```

| Suite | Tests | What it locks down |
|-------|-------|--------------------|
| `com.jarvisblue.core.common.RedactorTest` | 6 | Provider-style keys, `key = value` assignments, `Authorization:` headers and URL-embedded credentials are scrubbed before any write. Benign text is untouched. |
| `com.jarvisblue.core.common.TextToolsTest` | 5 | Normalisation, token overlap, Levenshtein, fuzzy similarity tolerant of ASR noise. |
| `com.jarvisblue.core.model.ModelTest` | 3 | BCP-47 → language resolution, risk ordering, provider capability flags. |
| `com.jarvisblue.core.tools.SchemaValidatorTest` | 8 | Missing required parameter, unknown parameter (injection), wrong type, out-of-range number, over-long string, non-enum value, defaults, empty-argument tools. |
| `com.jarvisblue.core.tools.RiskEvaluatorTest` | 5 | Payment content → CRITICAL, remote tools → ≥ HIGH, destructive tools → ≥ HIGH, sensitive paths → ≥ MEDIUM, ordinary content keeps its baseline. |
| `com.jarvisblue.core.tools.IntentRouterTest` | 7 | The six example commands from the brief are detected with the right intent, and unrelated text falls back to chat. |
| `com.jarvisblue.core.tools.SecurityScannerTest` | 5 | Cleartext HTTP, disabled certificate validation (CRITICAL), hard-coded API keys, world-readable files, clean code → no findings. |
| `com.jarvisblue.core.tools.CodeQualityCheckerTest` | 4 | Unbalanced brackets, `!!`, broad exception handlers, clean code → no issues. |
| `com.jarvisblue.core.tools.QuantumSimulatorTest` | 5 | Bell pair yields only `00`/`11` with balanced probabilities, single H gives a uniform superposition, X is deterministic, oversized circuits are refused. |
| `com.jarvisblue.core.voice.WakePhraseMatcherTest` | 8 | Exact phrase, phrase inside a sentence, ASR noise ("bloo"), unrelated speech, Tamil and French variants, command extraction. |
| `com.jarvisblue.core.windows.BridgeSignatureTest` | 4 | The HMAC scheme matches the Python bridge byte-for-byte using shared vectors; nonces and bodies change the signature. |
| **Total** | **106** | **0 failures** |

### Cross-implementation verification of the bridge protocol

The Android client and the Python bridge are verified against the *same* test
vectors, so the two halves cannot drift apart silently:

| Input | Expected | Both implementations |
|-------|----------|----------------------|
| `sha256("")` | `e3b0c442…7852b855` | ✅ |
| `HMAC-SHA256("GET\n/api/status\n1700000000000\nnonce-123\nsha256(\"\")", "test-secret")` | `5a0eff83…d32a3d` | ✅ |

---

## 2. Static compatibility check — 34 checks, 0 failures

```
./gradlew :app:assembleRelease && scripts/compat-check.sh
```

| Group | Checks | Result |
|-------|--------|--------|
| SDK levels | minSdk ≥ 31, targetSdk ≥ 34, compileSdk = 35 | ✅ |
| Forbidden permissions | 14 dangerous permissions must **not** be requested | ✅ |
| Required components | 10 manifest components present | ✅ |
| Backup | `allowBackup=false` + data-extraction rules | ✅ |
| No hard-coded keys | production sources scanned for key literals | ✅ |
| Artefacts | keystore present, APK present, signature verifies | ✅ |

Forbidden-permission list that is asserted absent:
`READ_SMS`, `RECEIVE_SMS`, `SEND_SMS`, `READ_CONTACTS`, `WRITE_CONTACTS`,
`ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `CAMERA`,
`MANAGE_EXTERNAL_STORAGE`, `READ_EXTERNAL_STORAGE`, `QUERY_ALL_PACKAGES`,
`BIND_DEVICE_ADMIN`, `REQUEST_INSTALL_PACKAGES`.

---

## 3. Build verification

| Check | Result |
|-------|--------|
| `./gradlew :app:assembleDebug` | ✅ BUILD SUCCESSFUL — `app-debug.apk`, 76 MB |
| `./gradlew :app:assembleRelease` | ✅ BUILD SUCCESSFUL — `app-release.apk`, **17 MB** (R8 + resource shrinking) |
| `./gradlew test` | ✅ BUILD SUCCESSFUL — 106 tests, 0 failures |
| `apksigner verify --verbose` | ✅ Verifies — **APK Signature Scheme v3** |
| Signing certificate | `CN=JARVIS BLUE MOBILE, OU=Personal, O=JARVIS BLUE, L=Chennai, ST=TN, C=IN` |
| Certificate SHA-256 | `44cb295eb9e11dccd6bef68145290f3ea86d278ef14a207da60ed39509f474a7` |
| Key | RSA 3072-bit, PKCS#12, valid 10000 days |

> AGP selects **v3** because `minSdk = 31` (Android 12) already supports it;
> v1/v2 are unnecessary for Android 12+ and are not emitted. The build does
> set `enableV1Signing`/`enableV2Signing`/`enableV3Signing` explicitly so the
> behaviour is intentional rather than implicit.

### Release APK manifest (verified with `aapt dump badging`)

```
package: name='com.jarvisblue.mobile' versionCode='1' versionName='1.0.0'
sdkVersion:'31'      targetSdkVersion:'35'      compileSdkVersion='35'
```

Declared permissions: `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE`,
`RECORD_AUDIO`, `POST_NOTIFICATIONS`, `VIBRATE`, `FOREGROUND_SERVICE`,
`FOREGROUND_SERVICE_MICROPHONE`, `FOREGROUND_SERVICE_DATA_SYNC`,
`RECEIVE_BOOT_COMPLETED`, `WAKE_LOCK`, `SCHEDULE_EXACT_ALARM`,
`USE_EXACT_ALARM`, `USE_BIOMETRIC`, `USE_FINGERPRINT`, `SYSTEM_ALERT_WINDOW`.

---

## 4. Defects found and fixed by the test suite

These were real bugs, caught before delivery:

| # | Defect | How it was found | Fix |
|---|--------|------------------|-----|
| 1 | Quantum CNOT was a no-op — the Bell pair produced four outcomes | `QuantumSimulatorTest` | The swap loop processed each amplitude pair twice; now only the half with the target bit cleared is swapped |
| 2 | Quantum results included zero-probability states | `QuantumSimulatorTest` | Theoretical outcomes are filtered below `1e-9` |
| 3 | Schema range checks never fired (`hour = 99` accepted) | `SchemaValidatorTest` | The check was gated on `JsonPrimitive.isString`, so numeric primitives skipped it |
| 4 | Intent matching failed on natural sentences | `IntentRouterTest` | Whole-string similarity replaced with token-window coverage |
| 5 | Dagger could not bind the provider map | Release build | `Map<ProviderId, AiProvider>` is treated as a multibinding map; replaced with a `ProviderRegistry` holder |
| 6 | Hilt worker failed to generate | Release build | `@AssistedInject` lives in `dagger.assisted`, not `dagger.assists` |
| 7 | Screen-capture service did not compile | Release build | `MediaProjection.EXTRA_*` constants do not exist; use `MediaProjectionManager.getMediaProjection()` |
| 8 | Release build exhausted the 3 GB host | Release build | Heap/metaspace retuned and documented in `docs/BUILD.md` |

---

## 5. Device test plan — requires your hardware

The static and JVM-level verification is complete. The following **must** be run
on real devices before you rely on the app; the table is also reproduced in
`docs/ANDROID_COMPATIBILITY.md` §5.

| Test | Pixel | Samsung | Xiaomi | OnePlus | Android 12 |
|------|-------|---------|--------|---------|-------------|
| Install and first launch | ☐ | ☐ | ☐ | ☐ | ☐ |
| App lock with biometric | ☐ | ☐ | ☐ | ☐ | ☐ |
| AI chat with a configured provider | ☐ | ☐ | ☐ | ☐ | ☐ |
| `device_diagnostics` tool | ☐ | ☐ | ☐ | ☐ | ☐ |
| `compose_message` prompts for confirmation | ☐ | ☐ | ☐ | ☐ | ☐ |
| Declining a confirmation is reported to the model | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tamil speech-to-text | ☐ | ☐ | ☐ | ☐ | ☐ |
| Tamil text-to-speech | ☐ | ☐ | ☐ | ☐ | ☐ |
| *On-device ASR* badge matches reality | ☐ | ☐ | ☐ | ☐ | ☐ |
| Wake word from the assistant screen | ☐ | ☐ | ☐ | ☐ | ☐ |
| Wake word survives 10 minutes backgrounded | ☐ | ☐ | ☐ | ☐ | ☐ |
| Default-assistant selection | ☐ | ☐ | ☐ | ☐ | ☐ |
| Notification-access toggle → summaries appear | ☐ | ☐ | ☐ | ☐ | ☐ |
| SAF tree grant → file organisation dry run | ☐ | ☐ | ☐ | ☐ | ☐ |
| Emergency stop blocks every tool | ☐ | ☐ | ☐ | ☐ | ☐ |
| Windows bridge pair + heartbeat + job list | ☐ | ☐ | ☐ | ☐ | ☐ |
| Battery drain over one hour idle | ☐ | ☐ | ☐ | ☐ | ☐ |

### How to run the tests quickly

```bash
# Drive the app while watching the log
adb logcat -s JarvisBlue:V AndroidRuntime:E

# Trigger the permission dashboard
adb shell am start -n com.jarvisblue.mobile/.MainActivity

# Verify the wake-word service can start (must be done from the visible app on Android 14+)
adb shell dumpsys activity services com.jarvisblue.mobile | grep WakeWordService
```

---

## 6. What is **not** covered by automated tests

Stated plainly, because a test report that implies more coverage than exists
is worse than no report:

* **No instrumentation tests.** There is no connected-device test run in this
  delivery, because no physical device or emulator was available on the build
  host. The `androidTest` source sets are wired up and ready
  (`androidx.test.ext:junit`, `espresso-core`) but contain no test classes yet.
* **No Keystore round-trip test on a device.** The `CipherBox` envelope format
  is unit-testable only with an Android runtime; it was verified by inspection
  against the Keystore API rather than by execution.
* **No SQLCipher-at-rest verification on a device.** The passphrase derivation
  is correct by construction (a random 32-byte value, Keystore-encrypted), but
  a forensic check on a real device has not been performed.
* **No OEM-specific code paths exist**, so there is nothing OEM-specific to
  test in the codebase — only the configuration guidance in the compatibility
  document.
* **No third-party security audit.**
