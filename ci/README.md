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

## The CI improvement patches

The App that pushes this repository has no `workflows` permission, so it
cannot write `.github/workflows/`. Every change to a workflow therefore
travels as a patch, and the owner applies them once.

`patches/github-actions-green.patch` turns off `fail-fast` in the desktop
test workflow, so a Linux only failure never hides the Windows result.

`patches/ci-libegl-failfast.patch` gives the Linux runner the Qt runtime
libraries it needs, so the suite can import PySide6 at all. It used to add
the `fail-fast` setting as well, with the very same lines that
`github-actions-green.patch` adds, so the two could not both be applied.
They now carry different halves of the same change, and the whole set
applies together.

`patches/ci-stack-verification.patch` makes the CI check the work while it
is still a pull request: the Android application is built on a pull request
that touches the phone, the rules of the phone in `:core:common` are run as
well, and the Windows installer is built for a pull request to any branch,
because the work arrives as a stack of branches.

`tests/test_workflow_patches.py` applies the whole set to a copy of the
tree and reads the workflows that come out, so the suite describes what
the build servers will really run.

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
