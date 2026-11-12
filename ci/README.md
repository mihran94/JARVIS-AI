# GitHub Actions workflow sources

These are the workflow files for this repository and for the Android client.
They live here because the connected GitHub App cannot write to
`.github/workflows/` (it has no `workflows` permission), so the owner applies
them with the prepared patches.

| File | Goes to | Repository |
| --- | --- | --- |
| `windows-release.yml` | `.github/workflows/windows-release.yml` | `mihran94/JARVIS-AI` |
| `android-debug-apk.yml` | `.github/workflows/android-debug-apk.yml` | `mihran94/jarvis-blue-android` |

## The shortest route

The repository `mihran94/jarvis-unified-builds` holds both workflow files in
their final form, and they build the two source repositories without touching
them. Copying the two files into that repository's `.github/workflows/` and
pushing starts both builds. The files there are the ones listed above.

## Applying them

In `mihran94/JARVIS-AI`, the patch fixes the failing runner and adds the
Windows build:

```
git apply patches/github-actions-green.patch
```

In `mihran94/jarvis-blue-android`, the patch adds the debug APK build:

```
git apply patches/android-debug-apk.patch
```

Both patches were verified with `git apply --check`.

## What they do

`windows-release.yml` runs the test suite on Windows, builds the unsigned
PyInstaller folder with PyInstaller, writes a release manifest with the
SHA-256 of every built file, and uploads the folder as the artifact
`JarvisAI-windows-x64`.

`android-debug-apk.yml` restores the Gradle wrapper from its base64 sidecar,
builds `:app:assembleDebug` with the automatic **debug** key, records the
SHA-256 of the APK and uploads it as `JarvisBlue-android-debug-apk`. The
release signing key is never involved: that key was exposed in a shareable
archive and must not be used by any workflow until it has been rotated. See
`../docs/ANDROID_SIGNING_KEY_ROTATION.md`.

## Granting the agent the permissions instead

If the connected GitHub App is given **Workflows: write** and **Actions:
write**, the agent can apply these files and re-run the workflows directly.
Without those two permissions the App can push ordinary source files but
cannot change or re-run a workflow.
