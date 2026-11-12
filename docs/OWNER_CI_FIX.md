# Owner action: the artefacts still need one permission

**Status: the test recipe is green.** Runs 43128880431, 43129242046 and
43129465299 on `main` have two jobs each and no failed job: the Ubuntu runner
and the Windows runner both pass the whole suite.

What is left is the two build workflows for the Windows application and the
Android APK. They need a file under `.github/workflows/`, and the connected
GitHub App cannot write one.

## The problem that was

`mihran94/JARVIS-AI` → `.github/workflows/tests.yml` runs the test suite on
`ubuntu-latest` and `windows-latest`. On the Linux runner the PySide6 import
fails before a single test is collected:

```
ImportError: libEGL.so.1: cannot open shared object file: No such file or directory
```

The runner has no EGL library, so `from PySide6.QtWidgets import QApplication`
dies. The six desktop test modules cannot be imported, pytest exits with
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

**The first change is not needed any more.** The runtime library is now
provided from the repository itself, by `scripts/qt_runtime.py` and the
repository `conftest.py`, so the whole suite runs on the Linux runner with no
change to the workflow file at all. It installs `libEGL.so.1` only when the
machine does not have it, only on Linux, and it can be switched off with
`JARVIS_SKIP_SYSTEM_PACKAGES=1`.

**The second change is still worth making.** With `fail-fast: false` a
failure on one operating system no longer hides the result of the other one.
That is exactly what hid the two Windows faults for so long.

With the Linux job green, the Windows job stopped being cancelled and ran for
the first time. It found two real faults, and both are fixed:

- an update archive member whose written name contains a backslash was
  accepted on Windows, because the zip module turns a backslash into a path
  separator while it reads an archive there. `core/updates.py` now checks the
  name as it was written, so the member is refused on every platform;
- three tests carried a test name longer than Windows allows in an
  environment variable, so they errored before they ran. They carry short
  names now.

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

**Actions: write is needed for the artefacts, not for the tests.** The tests
run on every push, so no permission is needed for them to run.

The repositories being public does not change this. The restriction is on the
permission of the token, not on the visibility of the repository: a GitHub App
without the `workflows` permission is refused when it writes a file under
`.github/workflows/`, for a public repository exactly as for a private one.

## The artefacts

This is the one part that still needs the owner, because a new workflow file
is needed and the connected GitHub App cannot write one.

**The shortest way to get there**: the repository
`mihran94/jarvis-unified-builds` holds both workflow files, ready to copy.
Copy them into that repository's own `.github/workflows/` and push:

```
cp windows-release.yml .github/workflows/windows-release.yml
cp android-debug-apk.yml .github/workflows/android-debug-apk.yml
git add .github/workflows && git commit -m "Add the JARVIS Unified AI build workflows" && git push
```

The push starts both builds. The source repositories are not touched by this
route, because the workflows check them out.

Once the workflows are in place, the artefacts are available from the run
pages:

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
