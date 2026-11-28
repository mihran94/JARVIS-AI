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


def test_coding_tests_drain_large_output_and_respect_timeout(tmp_path):
    import subprocess
    import sys

    from developer_studio.codex_task import run_local_tests

    def command(program):
        args = [sys.executable, '-c', program]
        if sys.platform == 'win32':
            return subprocess.list2cmdline(args)
        from shlex import join
        return join(args)

    status, output = run_local_tests(tmp_path, command("print('x' * 150000); print('finished')"), timeout=5)
    assert status == 'passed'
    assert output.endswith('finished\n')
    assert len(output) <= 8000
    status, output = run_local_tests(tmp_path, command("import time; time.sleep(10)"), timeout=0.15)
    assert status == 'failed'
    assert 'timed out' in output
