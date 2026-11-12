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
write to a file under `.github/workflows/` is rejected. The fix is prepared,
tested locally and shipped as a patch in `patches/`.

## The fix

Two changes to `.github/workflows/tests.yml`:

1. install the Qt runtime libraries on the Linux runner, and
2. set `fail-fast: false` so the Windows job is reported even when the Linux
   job fails.

### Option A — apply the patch (recommended)

```
git checkout integration/unified-foundation
git apply patches/ci-libegl-failfast.patch
git commit -m "Install the Qt runtime libraries on the Linux runner and report both operating systems"
git push
```

The patch was verified with `git apply --check` against the current workflow
file, and the result was compared with the intended fixed file.

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

Grant the connected GitHub App the **Workflows: write** permission, then ask
for the change to be applied. The App will then be able to write
`.github/workflows/tests.yml` directly.

## What to expect afterwards

The suite is the same one that runs locally:

```
239 passed, 3 skipped
```

on the branch before this work, and more with the router, bridge and voice
tests added on top. The three skipped tests are the Windows only ones, so the
Windows job is the one that really matters for the desktop acceptance checks.
