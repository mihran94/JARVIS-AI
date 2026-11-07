# JARVIS BLUE MOBILE — Build Guide

Everything below was executed on the machine that produced the delivered APKs.

---

## 0. First-time clone (do this once)

```bash
git clone https://github.com/mihran94/jarvis-blue-android.git
cd jarvis-blue-android

# 1. Restore the Gradle wrapper JAR
bash gradle/wrapper/restore-wrapper.sh

# 2. Restore the execute bit on the scripts
chmod +x gradlew gradlew.bat scripts/compat-check.sh
```

> **Why step 1?**
> This repository was published through an API that transports file contents as
> UTF-8 text, so the binary `gradle/wrapper/gradle-wrapper.jar` could not be
> committed as a binary blob. It is stored byte-exact as
> `gradle/wrapper/gradle-wrapper.jar.b64` (SHA-256
> `2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046`) and
> `restore-wrapper.sh` decodes it back into place. If you already have Gradle
> 8.11.1 installed, `gradle wrapper` regenerates it just as well.
>
> **Why step 2?**
> The same API creates files with mode `100644`, so `gradlew` and
> `scripts/compat-check.sh` arrive without the execute bit.

---

## 1. Toolchain

| Tool | Version used | Minimum |
|------|--------------|---------|
| JDK | OpenJDK **17.0.21** | 17 (AGP 8.7 requires 17) |
| Gradle | **8.11.1** (via the wrapper) | 8.11.1 |
| Android Gradle Plugin | **8.7.3** | 8.7.3 |
| Kotlin | **2.0.21** | 2.0.21 |
| KSP | 2.0.21-1.0.28 | matching Kotlin |
| Compose BOM | 2024.10.01 | — |
| compileSdk / targetSdk | **35** (Android 15) | 35 |
| minSdk | **31** (Android 12) | 31 |
| Build tools | 34.0.0 / 35.0.0 | 34.0.0 |

### Install the toolchain on a fresh machine

```bash
# 1. JDK 17
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk-headless unzip

# 2. Android SDK command-line tools
mkdir -p "$HOME/Android/sdk/cmdline-tools"
cd /tmp
curl -sSLO https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip -q commandlinetools-linux-11076708_latest.zip -d "$HOME/Android/sdk/cmdline-tools"
mv "$HOME/Android/sdk/cmdline-tools/cmdline-tools" "$HOME/Android/sdk/cmdline-tools/latest"

# 3. Accept licences and install the platforms
export ANDROID_HOME="$HOME/Android/sdk"
yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
  "platform-tools" "platforms;android-34" "platforms;android-35" \
  "build-tools;34.0.0" "build-tools;35.0.0"

# 4. Point the project at the SDK
echo "sdk.dir=$ANDROID_HOME" > local.properties
```

### Open in Android Studio

1. *File → Open* → select the `jarvis-blue-mobile` directory.
2. Android Studio uses the bundled Gradle wrapper — no separate Gradle install.
3. Wait for the initial sync (the first build downloads ~1 GB of dependencies).

---

## 2. Build the APKs

```bash
cd jarvis-blue-mobile
export ANDROID_HOME="$HOME/Android/sdk"

# Debug APK (installable for testing)
./gradlew :app:assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk

# Signed release APK (R8 minified + resource shrinking)
./gradlew :app:assembleRelease
# → app/build/outputs/apk/release/app-release.apk

# Unit tests
./gradlew test

# Everything the CI would run
./gradlew clean assembleDebug assembleRelease test lint
```

---

## 3. Release signing

The project ships with a **PKCS#12** keystore for private sideloading.

| Item | Value |
|------|-------|
| File | `keystore/jarvis-release.p12` |
| Alias | `jarvisblue` |
| Store / key password | `jarvisblue` |
| Algorithm | RSA 3072, SHA-256withRSA, valid 10000 days |

`keystore/keystore.properties` points the Gradle build at it.

> ⚠️ **This keystore is in the repository because the APK is for your own
> private device.** If you ever publish the app, generate your own keystore and
> delete this one:

```bash
keytool -genkeypair -v -keystore my-release.p12 -storetype PKCS12 \
  -keyalg RSA -keysize 3072 -validity 10000 -alias myalias \
  -storepass "$PASSWORD" -keypass "$PASSWORD" \
  -dname "CN=You, O=You, C=IN"

cat > keystore/keystore.properties <<EOF
storeFile=keystore/my-release.p12
storePassword=$PASSWORD
keyAlias=myalias
keyPassword=$PASSWORD
EOF
```

The signing configuration lives in `app/build.gradle.kts` and is applied only
to the `release` build type. The debug build is signed with the standard
Android debug key and uses the `.debug` application-id suffix
(`com.jarvisblue.mobile.debug`) so it can be installed alongside the release
build.

### Verify the signature

```bash
$ANDROID_HOME/build-tools/35.0.0/apksigner verify --verbose --print-certs \
  app/build/outputs/apk/release/app-release.apk
```

Expected: `Verifies` and `Verified using v3 scheme (APK Signature Scheme v3): true`.
AGP selects v3 because `minSdk = 31` already supports it; v1/v2 are not emitted
for Android 12+ targets.

---

## 4. Low-memory build hosts

The delivered build ran on a **2 vCPU / 3 GB RAM** container, which is tight
for an R8 release build of a 14-module Compose app. `gradle.properties` is
tuned for that:

```properties
org.gradle.jvmargs=-Xmx1024m -XX:MaxMetaspaceSize=900m -XX:+UseSerialGC -Dfile.encoding=UTF-8
org.gradle.parallel=false
kotlin.compiler.execution.strategy=in-process
```

If the daemon is killed during the release build, use these steps in order:

1. `./gradlew --stop` to drop the existing daemon.
2. Lower `-Xmx` to `768m` and raise `-XX:MaxMetaspaceSize` to `640m`.
3. Build the library modules first so the release variants are cached:
   `./gradlew :core:tools:assembleRelease :feature:chat:assembleRelease …`
4. If R8 still cannot fit, temporarily set `isMinifyEnabled = false` in the
   release build type. The app is fully functional either way — only the APK
   size changes. **On a workstation with 8 GB+ of RAM, keep R8 enabled.**

### If the build fails with `OutOfMemoryError: Metaspace`

Raise `-XX:MaxMetaspaceSize` and lower `-Xmx` by the same amount; the total
footprint is what matters in a 3 GB container.

### If the build fails with `SDK location not found`

`local.properties` must contain the absolute path:

```properties
sdk.dir=/home/you/Android/sdk
```

### If dependency resolution fails

The build needs access to `google()` and `mavenCentral()`. On a locked-down
network, configure a mirror in `settings.gradle.kts` or in
`~/.gradle/init.gradle.kts`.

### If the release APK is rejected by the device

- `INSTALL_FAILED_UPDATE_INCOMPATIBLE` → a different signing key signed the
  installed build. Uninstall the old copy first.
- `INSTALL_FAILED_VERSION_DOWNGRADE` → uninstall, or raise `versionCode`.
- `INSTALL_FAILED_NO_MATCHING_ABIS` → the SQLCipher native library is missing
  for your ABI. The AAR ships `arm64-v8a`, `armeabi-v7a`, `x86` and `x86_64`.

---

## 5. Windows bridge build

```powershell
cd windows-bridge
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# one-time: generate the shared secret
python -m jarvis_bridge.server --generate-secret

# run the bridge (keep it bound to localhost)
$env:JARVIS_BRIDGE_SECRET = "<paste the secret>"
python -m jarvis_bridge.server --host 127.0.0.1 --port 8765
```

The phone pairs with the same secret in *Control → Windows → Pair*.

---

## 6. Module dependency graph

```
app
 ├── feature:chat ────────▶ core:ai, core:tools, core:database, core:ui
 ├── feature:assistant ───▶ core:voice, core:ai, core:tools, core:ui
 ├── feature:studio ──────▶ core:ai, core:tools, core:ui
 ├── feature:command ─────▶ core:ai, core:tools, core:database, core:windows, core:security, core:ui
 └── core:model, core:common, core:security, core:database,
     core:ai, core:tools, core:voice, core:windows, core:ui

core:tools ──▶ core:ai, core:database, core:security, core:model, core:common
core:ai ────▶ core:database, core:security, core:model, core:common
core:database ▶ core:security, core:model, core:common
core:voice ──▶ core:security, core:model, core:common
core:windows ▶ core:database, core:security, core:model, core:common
core:ui ─────▶ core:model
```

There are no cycles. `core:model` and `core:common` are pure Kotlin JVM
modules and never touch the Android framework.

---

## 7. Repository layout

```
jarvis-blue-mobile/
├── app/                      Application module
├── core/
│   ├── model/ common/ security/ database/ ai/ tools/ voice/ windows/ ui/
├── feature/
│   ├── chat/ assistant/ studio/ command/
├── windows-bridge/           Reference Python desktop server
├── docs/                     This documentation set
├── scripts/compat-check.sh   Static compatibility checker
├── gradle/libs.versions.toml Version catalog
├── keystore/                 Private sideload signing key
├── gradlew / gradlew.bat     Gradle wrapper (8.11.1)
└── settings.gradle.kts       Module graph
```
