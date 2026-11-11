# Release readiness — integration branch

This file records what has been verified for the `integration/unified-foundation`
branch and what the owner still has to run on a real machine. Nothing here is
a claim that an artefact was built: no Windows executable, no APK and no
installer were produced in the environment used for this work.

## Verified in the integration environment

| Check | Result |
| --- | --- |
| Test suite | `239 passed, 3 skipped` |
| Baseline before the branch work | `175 passed, 3 skipped` |
| Byte compilation | `python -m compileall -q .` exit code 0 |
| Pushed file contents | Every pushed file read back from the branch and compared with the locally validated copy |

Environment: Linux, Python 3.11.2, PySide6 6.8.3, httpx 0.28.1, keyring 25.6.0,
pytest 8.3.5, Qt offscreen platform. The repository targets Python 3.12.

No API key was configured or created, no provider was called, no device was
paired, no bridge socket was bound and no code from a provider response was
executed.

The 3 skipped tests are the Windows only ones. See `docs/TEST_RESULTS.md` for
the full record.

## Still to be done on the owner's Windows PC

### Desktop application

```
setup.cmd                 REM creates .venv and installs the pinned dependencies
scripts\test.cmd          REM runs the same suite
START_JARVIS.cmd          REM starts the application
installers\build.cmd      REM optional PyInstaller folder build
```

Notes that matter for a release decision:

- `installers\build.cmd` produces an **unsigned** PyInstaller folder. It is not
  a signed installer and not a release artefact.
- Credential storage works only on Windows. On other systems the vault raises
  instead of falling back to a plaintext file.
- Review the PySide6 and Qt licensing before any redistribution. No SBOM and
  no dependency lock beyond the direct pins exist yet.
- The database is plain user data under `%LOCALAPPDATA%\JarvisAI`. Back up
  that folder before an upgrade. `ROLLBACK_JARVIS.cmd` and
  `scripts/rollback_update.py` cover the upgrade path.

### Android client

The Android application is a separate repository and is not built by this
branch. In `mihran94/jarvis-blue-android`:

```
bash gradle/wrapper/restore-wrapper.sh
chmod +x gradlew gradlew.bat scripts/compat-check.sh
./gradlew :app:assembleDebug
```

The release variant needs the owner's signing keystore, which is deliberately
not in the repository and must not be added to it. Installation steps are in
that repository's `docs/INSTALL.md`.

The Android release workflow publishes only when it is dispatched manually and
the release confirmation input is set. It is not part of a normal pull request.

## Source integrity

`docs/SOURCE_INTEGRITY.sha256` lists the SHA-256 of every source file on this
branch, in `sha256sum` format. Verify the tree before building:

```
sha256sum -c docs/SOURCE_INTEGRITY.sha256
```

On Windows PowerShell, compare with:

```
Get-FileHash -Algorithm SHA256 <file>
```

The manifest deliberately does not list itself. Every other file on the branch
is covered.

## Blockers

1. **The hosted CI is red for an environment reason, not a code reason.** On
   `ubuntu-latest` the PySide6 import fails with `ImportError: libEGL.so.1`,
   so the desktop tests cannot be collected, and `fail-fast` cancels the
   Windows job. The same failure occurs on the base commit. The fix is a
   `libegl1` install step plus `fail-fast: false`, and it **could not be
   pushed** because the connected GitHub App has no `workflows` permission. It
   needs either that permission for the App or one commit from the owner.

2. **The provider router is not wired into the desktop yet.** The application
   still calls `providers.chat` directly, so Claude and the local Ollama model
   are not reachable from the interface yet. The router and both adapters are
   implemented and tested, but a user cannot select them.

3. **The bridge has no listener and no desktop surface.** The protocol and its
   desktop handler are implemented and tested, but nothing binds a socket and
   the interface does not show a pairing or job screen. A phone cannot reach
   the application today.

4. **No voice.** The desktop has no speech input or output. The Android client
   has voice, but that code is Kotlin and cannot be reused by a PySide6
   process. A desktop voice adapter with an explicit microphone consent and a
   stop control is still to be designed.

5. **No Windows or Android build was executed here**, so no artefact hash,
   installer or APK is claimed.
