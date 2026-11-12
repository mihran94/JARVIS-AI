# Owner action: what is left is one dispatch and one file

**Status of the test recipe: green.** Runs 43128880431, 43129242046,
43129465299, 43129837943, 43131805606, 43132136357, 43139374013 and
43141256056 on `main` each have two jobs and no failed job: the Ubuntu
runner and the Windows runner both pass the whole suite.

The Linux runner needed a Qt runtime library that it does not have. That is
now installed **from the repository content** — `scripts/qt_runtime.py` plus
the `conftest.py` at the root, which runs before any test module is imported.
The workflow file did not have to change, so the recipe is green today.

Two things are still the owner's, because the connected GitHub App cannot
write `.github/workflows/` and cannot dispatch a workflow run.

## 1. The Windows build — one click

`mihran94/JARVIS-AI` already carries `.github/workflows/windows-release.yml`
and GitHub reports the workflow as **active**. Nothing has to be copied.

1. Open the repository → **Actions** → **Windows desktop build**.
2. Press **Run workflow** and choose the branch `main`.

The job runs the test suite, builds the unsigned PyInstaller folder, writes
the release manifest with the SHA-256 of every built file and uploads the
folder as the artefact `JarvisAI-windows-x64`. Download it from the run
page.

The workflow also runs on a push that touches the workflow file itself, but a
normal commit does not touch it, so a dispatch is the shortest route.

**Not yet proven.** This workflow has never run. The test suite passes on
Windows, but the PyInstaller step has never been executed. If it fails, the
job log says which module was missing; `--hidden-import keyring.backends.Windows`
is already in the command for the one dynamic import that the desktop uses.

## 2. The Android APK build — one file

`mihran94/jarvis-blue-android` has no APK build workflow yet. The owner adds
it and pushes:

```
git clone https://github.com/mihran94/jarvis-blue-android
cd jarvis-blue-android
git checkout fix/gemini-voice-android12-v118-20261109
git apply patches/android-debug-apk.patch
git commit -am "ci: build the Android debug APK"
git push
```

The patch was verified with `git apply --check`. The push matches the path
filter (`app/**`, `core/**`, `feature/**`), so the job starts by itself: it
restores the Gradle wrapper from its base64 sidecar, builds `:app:assembleDebug`
with the automatic **debug** key, records the APK SHA-256 and uploads the
artefact `JarvisBlue-android-debug-apk`.

The exposed release key is not used by that workflow and must not be used by
any workflow until it has been rotated. See
`docs/ANDROID_SIGNING_KEY_ROTATION.md`.

## 3. The optional CI improvement

`patches/github-actions-green.patch` carries one change to the test
workflow: `fail-fast: false`, so a Linux only problem never hides the
Windows result. The Qt runtime library is already handled by the repository
content, so this patch is a nicety, not a fix.

```
git apply patches/github-actions-green.patch
```

It was verified with `git apply --check` against the current `main`.

## What the agent would need to do this itself

| Permission | What it allows |
| --- | --- |
| **Workflows: write** | writing `.github/workflows/*` |
| **Actions: write** | dispatching, re-running and cancelling workflow runs |

With both, the agent could apply the workflow files, start the runs and
read the job logs without the owner.
