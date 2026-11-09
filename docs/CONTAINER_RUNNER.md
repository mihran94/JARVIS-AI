# Experimental Python container runner

Command-line foundation only; not yet a desktop Run button or autonomous debugger. Requires separately installed local Docker in Linux-container mode and a trusted installed Python 3.12 image providing /usr/local/bin/python. No automatic installation, image download, daemon change or host execution fallback.

## Review and run

Obtain the full sha256 image ID from your reviewed image with `docker image inspect --format "{{.Id}}" python:3.12-slim`. Use a trusted official image. Tags are not accepted by the runner. Windows images and images declaring volumes are rejected. The runner uses the local socket/pipe, ignoring remote contexts and client proxy defaults.

From the project folder:

```powershell
.venv\Scripts\python.exe scripts\run_python_container.py reviewed.py --image sha256:YOUR_FULL_IMAGE_ID
```

This prints a digest without running code. After reviewing the source and image, repeat with `--approve` followed by that digest. Changes to the source or image invalidate approval. Each CLI invocation is a new explicit run request. Ctrl+C requests cleanup. The callback cancellation interface is available for future UI integration.

Output includes status, exit code and bounded untrusted program text. Paste a traceback into Developer Studio to request repair with separate approval; nothing is automatically uploaded.

## Restrictions

No host mounts, published ports or container networking. Read-only root filesystem and a 16 MB temporary /tmp. UID/GID 65534, all capabilities dropped, no-new-privileges. Limits: 256 MB memory, one CPU, 32 processes, 5-second CPU limit, 20-second execution timeout, 64 KiB captured output. Setup and cleanup have separate bounded waits. Docker logging is disabled. Removal is requested on every execution exit path; cleanup failure is reported with the generated container name.

Only one source file is sent through stdin. Interactive input, GUI apps, package installation and multi-file projects are unsupported. Temporary output files disappear on cleanup. Container isolation is not a guarantee against kernel/runtime vulnerabilities; hostile code needs a dedicated VM. The image and Docker installation are trusted dependencies.

## Verification

153 local tests passed; 3 Docker acceptance tests skipped. Compilation passed. Simulated-process tests cover approval mismatch, missing Docker, restrictive arguments, unsupported images, timeout, cancellation, output overflow, failed start and failed cleanup. These tests do not prove actual container isolation.

Docker executable is absent here. On a prepared test machine, explicitly set JARVIS_CONTAINER_TESTS=1 and JARVIS_TEST_IMAGE_ID to the trusted full image ID, then run `python -m pytest -q tests/test_container_integration.py`. Benign programs check output, blocked outbound networking and read-only root. Windows Docker Desktop validation remains pending.

Reference: https://docs.docker.com/engine/containers/run/

தமிழ்: இது experimental command-line வசதி. Docker மற்றும் trusted Python image முன்பே இருக்க வேண்டும். Code review செய்து digest approve செய்தால் மட்டுமே run ஆகும். Desktop Run button இன்னும் சேர்க்கப்படவில்லை.
