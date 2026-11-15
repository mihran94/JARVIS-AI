import os
import sys

import pytest

from developer_studio.codex_cli import run_codex


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX executable fixture")
def test_codex_reads_stdin_and_returns_answer_from_selected_project(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    executable = tmp_path / "codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "from pathlib import Path\n"
        "assert sys.argv[1:4] == ['--ask-for-approval', 'never', 'exec']\n"
        "assert sys.argv[sys.argv.index('--sandbox') + 1] == 'read-only'\n"
        "assert sys.argv[-1] == '-'\n"
        "assert Path.cwd().name == 'project with spaces'\n"
        "Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_text("
        "sys.stdin.read(), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    prompt = "இந்த project-ஐ review பண்ணு"
    assert run_codex(executable, project, prompt, lambda: None) == prompt
    assert not list(project.iterdir())
