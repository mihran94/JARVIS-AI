"""Run the installed Codex CLI against a selected project in read-only mode."""
from pathlib import Path
import os
import shutil
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic


def codex_executable():
    name = "codex.exe" if os.name == "nt" else "codex"
    path = shutil.which(name)
    if path is None and os.name == "nt":
        # npm installs a cmd shim and a native executable in its platform package.
        shim = shutil.which("codex.cmd")
        if shim:
            npm_root = Path(shim).parent / "node_modules" / "@openai" / "codex"
            candidates = [
                *npm_root.glob("node_modules/@openai/codex-win32-*/vendor/*/codex/codex.exe"),
                *npm_root.glob("vendor/*/codex/codex.exe"),
            ]
            if len(candidates) == 1:
                path = str(candidates[0])
    if path is None:
        raise ValueError("Install Codex CLI, add it to PATH, sign in with codex login, and restart JARVIS.")
    return Path(path).resolve(strict=True)


def run_codex(executable, project, prompt, check_cancelled):
    with TemporaryDirectory(prefix="jarvis-codex-") as directory:
        output = Path(directory) / "answer.txt"
        command = [
            str(executable), "--ask-for-approval", "never", "exec",
            "--ignore-user-config", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "--output-last-message", str(output), "-",
        ]
        check_cancelled()
        deadline = monotonic() + 300
        with subprocess.Popen(
            command, cwd=project, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process:
            try:
                pending = prompt.encode("utf-8")
                while True:
                    check_cancelled()
                    if monotonic() >= deadline:
                        raise ValueError("Codex took more than five minutes. Try a smaller task.")
                    try:
                        process.communicate(pending, timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        pending = None
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        check_cancelled()
        if process.returncode or not output.is_file():
            raise ValueError("Codex could not complete the request. Check codex login status and update the CLI if needed.")
        with output.open(encoding="utf-8") as response:
            answer = response.read(200_001)
        if not answer.strip():
            raise ValueError("Codex returned an empty response.")
        if len(answer) > 200_000:
            raise ValueError("Codex response exceeded the JARVIS display limit.")
        return answer
