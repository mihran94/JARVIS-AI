"""Command-first JARVIS: offline parser tests, no provider or OS execution."""
from developer_studio.commands import HELP, parse_command
from developer_studio.projects import SavedProject


PROJECTS = [
    SavedProject("project-a", "/tmp/project-a", "VS Code", "pytest -q"),
    SavedProject("AI Creative Studio", "/tmp/creative", "VS Code", "pytest -q"),
]


def test_minimal_navigation_and_help():
    assert parse_command("/island").kind == "island"
    assert parse_command("eyeland").kind == "island"
    assert parse_command("open settings").target == "Settings & Safety"
    assert parse_command("/settings").target == "Settings & Safety"
    assert parse_command("/code").target == "Coding Assistant"
    assert parse_command("/voice").target == "Voice / Hey Jarvis"
    assert parse_command("/new").kind == "new"
    assert "/project NAME fix GOAL" in HELP


def test_project_commands_only_accept_saved_projects():
    assert parse_command("/projects", PROJECTS).kind == "projects"
    assert parse_command("/project add", PROJECTS).kind == "project_add"
    assert parse_command("/project project-a", PROJECTS).kind == "project_status"
    assert parse_command("/project project-a open", PROJECTS).kind == "project_open"
    assert parse_command("/project project-a test", PROJECTS).kind == "project_test"
    change = parse_command("/project AI Creative Studio fix the login page", PROJECTS)
    assert change.kind == "project_fix"
    assert change.target == "AI Creative Studio"
    assert change.detail == "the login page"


def test_unknown_commands_cannot_become_shell_or_paid_cloud_requests():
    for query in ("/cmd shutdown", "/powershell rm -rf files", "/project unknown fix all",
                  "/project project-a; delete files", "/project project-a fix"):
        assert parse_command(query, PROJECTS).kind == "error"
    for query in ("what is machine learning?", "help with Python code",
                  "hello Jarvis", "how do I fix a project?"):
        assert parse_command(query, PROJECTS) is None
    assert parse_command(None, PROJECTS) is None
