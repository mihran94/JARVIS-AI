# Owner action: fix the GitHub Actions Linux runner

## The problem

`mihran94/JARVIS-AI` → `.github/workflows/tests.yml` runs the test suite on
`ubuntu-latest` and `windows-latest`. On the Linux runner the PySide6 import
fails before a single test is collected:

```
ImportError: libEGL.so.1: cannot open shared object file: No such file or directory
```

The runner has no EGL library, so `from PySide6.QtWidgets import QApplication`
dies. The five desktop test modules cannot be imported, pytest exits with
code 2, and because `fail-fast` is on by default the Windows job is cancelled
before it runs.

This is **not** caused by any recent change. The same failure occurs on the
base commit `2ae28c45c`:

https://github.com/mihran94/JARVIS-AI/actions/runs/43122781774

## Why it was not fixed here

The connected GitHub App does not hold the `workflows` permission, so every
write to a file under `.github/workflows/` is rejected. It does not hold the
`actions` permission either, so the agent cannot re-run a workflow run.

Two permissions unblock everything:

| Permission | What it allows |
| --- | --- |
| **Workflows: write** | writing `.github/workflows/*` |
| **Actions: write** | re-running and cancelling workflow runs |

The fix is prepared, checked with `git apply --check` and shipped as a patch.

## The fix

Two changes to `.github/workflows/tests.yml`:

1. install the Qt runtime libraries on the Linux runner, and
2. set `fail-fast: false` so the Windows job is reported even when the Linux
   job fails.

### Option A — apply the patch (recommended)

In `mihran94/JARVIS-AI`:

```
git checkout integration/unified-foundation
git apply patches/github-actions-green.patch
git commit -m "Install the Qt runtime libraries on the Linux runner and report both operating systems"
git push
```

That one patch does three things:

1. installs the Qt runtime libraries on the Linux runner,
2. sets `fail-fast: false` so the Windows job is reported instead of
   cancelled,
3. adds `.github/workflows/windows-release.yml`, which builds the Windows
   application and uploads it as an artifact.

In `mihran94/jarvis-blue-android`:

```
git apply patches/android-debug-apk.patch
git commit -m "Add the Android debug APK build"
git push
```

That patch adds `.github/workflows/android-debug-apk.yml`, which builds the
debug APK with the automatic debug key and uploads it as an artifact. The
release signing key is never used by it.

Both patches were verified with `git apply --check` against the current
workflow files.

### Option B — edit the file by hand

Under `jobs.test`:

```yaml
    strategy:
      # Report both operating systems even when one fails, so a Linux only
      # problem never hides the Windows result.
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
```

and add one step before the pip install:

```yaml
      - name: Install the Qt runtime libraries
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            libegl1 libglib2.0-0 libdbus-1-3 libxkbcommon0 libfontconfig1
```

### Option C — let the agent push it

Grant the connected GitHub App **Workflows: write** and **Actions: write**,
then ask for the change to be applied and the workflows to be re-run. The App
can then write `.github/workflows/*` directly and re-run the failed run.

## The artefacts

After the workflows are in place and green, the artefacts are available from
the run pages:

| Artefact | Workflow | Name |
| --- | --- | --- |
| Windows application folder | `windows-release.yml` | `JarvisAI-windows-x64` |
| Windows release manifest | `windows-release.yml` | inside the same artifact |
| Android debug APK | `android-debug-apk.yml` | `JarvisBlue-android-debug-apk` |
| APK SHA-256 | `android-debug-apk.yml` | inside the same artifact |

Both are downloadable from the workflow run page and from the repository
Actions tab. The Windows build is an **unsigned** PyInstaller folder, not a
signed installer.

## What to expect afterwards

The suite is the same one that runs locally:

```
239 passed, 3 skipped
```

on the branch before this work, and more with the router, bridge and voice
tests added on top. The three skipped tests are the Windows only ones, so the
Windows job is the one that really matters for the desktop acceptance checks.
