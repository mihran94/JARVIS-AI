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
    assert parse_command("/workspace").target == "Coding Assistant"
    for command in ("/files", "/folders", "/upload", "/attach", "file upload pannu",
                    "folder upload pannu", "கோப்புகளைத் திற"):
        parsed = parse_command(command)
        assert parsed.kind == "page"
        assert parsed.target == "Files & Folders"
    assert parse_command("/editors").kind == "editors"
    assert parse_command("/draft a Python hello world script").kind == "code_draft"
    assert parse_command("/draft a Python hello world script").detail == "a Python hello world script"
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
    # Keep the older local and video command handlers operational.
    for value in ("/status", "/time", "/capabilities", "/video make a short reel"):
        assert parse_command(value, PROJECTS) is None


def test_commands_for_analysis_and_fix_test_keep_the_requested_text():
    analysis = parse_command('ஜார்விஸ், /analyze How should I fix project-a?')
    assert (analysis.kind, analysis.detail) == ('analysis', 'How should I fix project-a?')
    task = parse_command('/project AI Creative Studio fix and test login page', PROJECTS)
    assert (task.kind, task.target, task.detail) == (
        'project_fix_test', 'AI Creative Studio', 'login page')
