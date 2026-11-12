# GitHub Actions workflow sources

These are the workflow files for this repository and for the Android client.
They live here because the connected GitHub App cannot write to
`.github/workflows/` (it has no `workflows` permission), so the owner applies
them with the prepared patches or starts them by hand.

| File | Goes to | Repository | State |
| --- | --- | --- | --- |
| `windows-release.yml` | `.github/workflows/windows-release.yml` | `mihran94/JARVIS-AI` | already on `main`, only needs a dispatch |
| `android-debug-apk.yml` | `.github/workflows/android-debug-apk.yml` | `mihran94/jarvis-blue-android` | one patch away |

## The Windows build is already on `main`

`mihran94/JARVIS-AI` already carries `.github/workflows/windows-release.yml`
and GitHub reports the workflow as **active**. Nothing has to be copied for
the Windows build.

The connected GitHub App cannot dispatch a workflow run, so the owner starts
it from the browser:

1. Open the repository → **Actions** → **Windows desktop build**.
2. Press **Run workflow** and choose the branch `main`.
3. The job runs the test suite, builds the unsigned PyInstaller folder,
   writes the release manifest and uploads the folder as the artifact
   `JarvisAI-windows-x64`.

The workflow only runs on a push that touches the workflow file itself, so a
normal commit does not start it. A dispatch is the shortest route.

## The Android build still needs one file

`mihran94/jarvis-blue-android` has no APK build workflow yet. The owner adds
it with the prepared patch:

```
git apply patches/android-debug-apk.patch
git commit -am "ci: build the Android debug APK"
git push
```

The push matches the path filter (`app/**`, `core/**`, `feature/**`), so the
job starts by itself and uploads the artifact `JarvisBlue-android-debug-apk`.

The patch was verified with `git apply --check`.

## The CI improvement patch

`patches/github-actions-green.patch` now only carries the change to the test
workflow: it reports both operating systems even when one of them fails, so a
Linux only problem never hides the Windows result. The Qt runtime library
that the Linux job needs is installed from the repository content
(`scripts/qt_runtime.py`), so the recipe is already green without this
patch.

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
