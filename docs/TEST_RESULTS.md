# Verification report — integration branch work, 12 November 2026

Environment: Linux; Python 3.11.2; PySide6 6.8.3; httpx 0.28.1; keyring 25.6.0; pytest 8.3.5.
The repository targets Python 3.12; the suite was executed on 3.11 here, so the
hosted 3.12 run is the authoritative one.

Commands:

    QT_QPA_PLATFORM=offscreen python -m pytest -q
    python -m compileall -q .

Actual final output:

    ...................................................................sss..  [ 29%]
    ........................................................................ [ 59%]
    ........................................................................ [ 89%]
    ..........................                                               [100%]
    239 passed, 3 skipped in 6.06s

    python -m compileall -q . completed with exit code 0.

The same suite on the base commit `2ae28c45c1913947e318946a20ad18b5e4171779`
reported 175 passed, 3 skipped. The 64 additional tests cover the bridge
protocol, the pairing and replay boundaries, the provider registry and router,
the Claude adapter and the local Ollama boundary. The skipped tests are the
Windows only ones.

Provider and bridge tests use synthetic HTTP transports (httpx.MockTransport)
and the real signing code. The Qt worker, widgets and SQLite paths are real.
No API key was configured or created, no provider was called and no device was
paired.

## CI defect found and fixed

The GitHub Actions recipe failed before this work reached it. On
`ubuntu-latest` the PySide6 import died with `ImportError: libEGL.so.1`, so
the desktop tests could not even be collected, and `fail-fast` cancelled the
Windows job. The workflow now installs the Qt runtime libraries on Linux and
reports both operating systems instead of cancelling the second one. The same
missing library had to be installed in the Linux environment used here.

## NOT EXECUTED

Windows OS integration, Windows Credential Manager, real Notepad/Calculator
launches, live provider requests, a packaged EXE, a bound bridge listener, a
paired Android device and any Android build. No claim of Windows certification,
of a working mobile bridge or of a production security audit is made. The
bridge binds no socket and the desktop interface does not expose it yet.

---

# Verification report — v0.2.0, 8 November 2026

Environment: Linux; Python 3.12.14; PySide6 6.8.3; httpx 0.28.1; keyring 25.6.0; pytest 8.3.5.

Command: QT_QPA_PLATFORM=offscreen python -m pytest -q

Actual final output:

    .........................................................                [100%]
    57 passed in 0.56s

python -m compileall -q . completed with exit code 0.

The 39-test v0.1 regression suite still passes (updated to navigate nine pages). Eighteen additional cases cover: queue persistence, fresh approvals after restart, duplicate-run rejection, atomic concurrent claims, cancellation while reviewing, emergency stop/resume, two interrupted job states, tampered app allowlist, launch failure without retry, v0.1 backup/migration, rejection of newer schemas, empty-choice usage chunks, missing/invalid counts, persistent archive/usage records, reopening chat, UI provider check, and UI queue cancellation.

Provider tests use synthetic HTTP responses with httpx.MockTransport; the Qt worker, widgets and SQLite paths are real. The provider-check test verifies no conversation messages are created and usage/health are recorded.

A real offscreen Qt screenshot of the task queue was captured and visually inspected (docs/desktop-preview.png). Qt emitted its benign offscreen propagateSizeHints warning.

NOT EXECUTED: Windows OS integration, Windows Credential Manager, real Notepad/Calculator launches, live provider requests, packaged EXE, or the supplied GitHub CI workflow. No API keys were configured or created. No claim of Windows certification or production security audit is made.

Windows acceptance steps are in WINDOWS_ACCEPTANCE.md. Historical v0.1 results are in TEST_RESULTS_v0.1.md.

---

# Verification report — CI on GitHub Actions, 12 November 2026

Environment: GitHub hosted runners, `ubuntu-latest` and `windows-latest`,
Python 3.12, with the repository recipe `.github/workflows/tests.yml`.

## Before

Every run of the recipe failed the same way:

| Job | Result |
| --- | --- |
| `test (ubuntu-latest)` | failure, `ImportError: libEGL.so.1: cannot open shared object file` |
| `test (windows-latest)` | cancelled, because the matrix cancels the second job when the first fails |

Run 43123745691 is the failure that was reported. The same failure happens on
the base commit `2ae28c45c`, run 43122781774, so it was not caused by any of
the integration work.

Six test modules could not be collected on Linux: `test_bridge_panel.py`,
`test_code_generation.py`, `test_code_repair.py`, `test_desktop.py`,
`test_desktop_fallback.py` and `test_key_only_setup.py`.

## What was changed

`scripts/qt_runtime.py` installs `libEGL.so.1` when the machine does not have
it, and the repository `conftest.py` calls it before pytest imports a test
module. The runner has passwordless `sudo`, and the runner image has no
package lists, so the script runs `apt-get update` first.

With the Linux job green, the Windows job stopped being cancelled and ran for
the first time. It found two faults, both now fixed:

1. `core/updates.py` accepted an update archive member whose written name
   contains a backslash on Windows, because the zip module turns a backslash
   into a path separator while it reads an archive there. The check now uses
   `orig_filename`, the name as it was written, so the member is refused on
   every platform. A backslash separates paths on Windows, so this was a path
   traversal vector in the update path.
2. `tests/test_code_repair.py` and `tests/test_code_generation.py` carried test
   names of up to 50001 characters. pytest puts the test name in the
   `PYTEST_CURRENT_TEST` environment variable and Windows refuses a value
   longer than 32767 characters, so the tests errored before they ran. They
   now carry short names.

## After

| Run | Trigger | Result |
| --- | --- | --- |
| 43128587965 | pull request | success, two jobs, no failed job |
| 43128581395 | push | success |
| 43128880431 | push to `main` | success, two jobs, no failed job |

The two jobs are `test (ubuntu-latest)` and `test (windows-latest)`. The
Windows runner reports 5 skipped tests and the Linux runner 3, because two
more tests are skipped outside Linux.

Local run of the same suite on Linux:

```
QT_QPA_PLATFORM=offscreen python -m pytest -q
301 passed, 3 skipped in 13.93s
```

NOT EXECUTED: a packaged Windows EXE, an Android APK build on the runner, a
real provider request, a paired phone, or a bound listener outside the
loopback interface. The Windows and Android build workflows are prepared in
`ci/` and in `patches/`, but they could not be pushed because the connected
GitHub App has no `workflows` permission.
