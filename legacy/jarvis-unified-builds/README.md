# JARVIS Unified AI — build pipeline

This repository holds the two build workflows for the JARVIS Unified AI
system. The source code stays in its own repositories; these workflows only
check the source out, build it and upload the result as an artefact.

| Workflow | Builds | Artefact name |
| --- | --- | --- |
| `windows-release.yml` | The PySide6 desktop application from `mihran94/JARVIS-AI` | `JarvisAI-windows-x64` |
| `android-debug-apk.yml` | The Android debug APK from `mihran94/jarvis-blue-android` | `JarvisBlue-android-debug-apk` |

Both use the standard GitHub hosted runners, `windows-latest` and
`ubuntu-latest`. No larger runner is used.

## One step is left

The two files in this repository are the workflow sources. They have to be
placed in `.github/workflows/` of this repository for GitHub to run them:

```
cp windows-release.yml .github/workflows/windows-release.yml
cp android-debug-apk.yml .github/workflows/android-debug-apk.yml
git add .github/workflows
git commit -m "Add the JARVIS Unified AI build workflows"
git push
```

The push starts both builds. After that the artefacts are on the run pages of
this repository, in the Actions tab.

The connected GitHub App that prepared this repository is not allowed to write
files under `.github/workflows/`, which is why this step is left to the owner.
Making the repositories public did not change that: the restriction is on the
permission of the token, not on the visibility of the repository.

## What the Windows build does

1. checks out `mihran94/JARVIS-AI` at `main`,
2. installs the pinned dependencies and runs the whole test suite, so a build
   is never made from a failing tree,
3. builds the unsigned PyInstaller folder with the same flags as the
   repository's own `installers\build.cmd`,
4. writes a release manifest with the SHA-256 of every built file, and
5. uploads the folder and the manifest as `JarvisAI-windows-x64`.

The build is an unsigned folder build, not a signed installer.

## What the Android build does

1. checks out `mihran94/jarvis-blue-android` at
   `fix/gemini-voice-android12-v118-20261109`,
2. restores the Gradle wrapper from its base64 sidecar,
3. builds `:app:assembleDebug` with the automatic **debug** key,
4. records the SHA-256 of the APK, and
5. uploads the APK and the digest as `JarvisBlue-android-debug-apk`.

The release signing key is not used by this workflow. That key was exposed
inside a shareable archive and must not be used until it has been rotated. A
release build without a keystore is refused by the build script itself, with
a clear message.

## Where the artefacts are found

Open the Actions tab of this repository, open a run, and download the artefact
at the bottom of the run page. The download keeps the name of the artefact
above. A run that was triggered by hand is found under
**Actions → Windows desktop build → Run workflow**, and the same for the
Android build.
