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


def run_codex(executable, project, prompt, check_cancelled, *, sandbox='read-only',
              approval='never', cwd=None, timeout=300):
    """Ask the Codex CLI to do something in a folder.

    The default is read-only, which is what the existing "Ask Codex about a
    project" action uses and must keep using.

    `sandbox` may be raised to 'workspace-write' when the caller has already
    isolated the work in a throwaway Git worktree of its own. Even then the
    CLI is told never to ask for approval, because the owner approves the
    whole action once, in the chat, before anything starts.

    `cwd` is the folder the CLI actually runs in. It is separate from
    `project` so a task can run in an isolated worktree while still being
    described in terms of the project the owner chose.
    """
    if cwd is None:
        # The default is the project the owner chose, exactly as before.
        cwd = project
    return _run_codex(executable, Path(cwd), prompt, check_cancelled,
                       sandbox=sandbox, approval=approval, timeout=timeout)


def _run_codex(executable, cwd, prompt, check_cancelled, *, sandbox, approval, timeout):
    with TemporaryDirectory(prefix="jarvis-codex-out-") as directory:
        output = Path(directory) / "answer.txt"
        command = [
            str(executable), "--ask-for-approval", approval, "exec",
            "--ignore-user-config", "--ephemeral", "--sandbox", sandbox,
            "--skip-git-repo-check", "--output-last-message", str(output), "-",
        ]
        check_cancelled()
        deadline = monotonic() + timeout
        with subprocess.Popen(
            command, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process:
            try:
                pending = prompt.encode("utf-8")
                while True:
                    check_cancelled()
                    if monotonic() >= deadline:
                        raise ValueError(f"Codex took more than {int(timeout // 60)} minutes. "
                                         "Try a smaller task.")
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
