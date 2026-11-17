"""Explicit, allowlisted commands for the single JARVIS assistant surface.

Never interprets free-form chat as a shell command. Destructive work is routed
through the existing Codex task approval and isolated worktree; project names
must already be saved in Settings.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    kind: str
    target: str = ""
    detail: str = ""


PAGE_COMMANDS = {
    "settings": "Settings & Safety",
    "plugins": "Settings & Safety",
    "coding": "Coding Assistant",
    "code": "Coding Assistant",
    "workspace": "Coding Assistant",
    "pc": "PC Control",
    "voice": "Voice / Hey Jarvis",
    "mobile": "Phone Remote",
    "memory": "Memory",
    "video": "Video Editor",
    "business": "Business",
    "providers": "AI Providers",
    "tasks": "Task Queue",
    "workflows": "Step Workflows",
    "history": "Task History",
    "review": "Review changes",
    "usage": "System & Usage",
    "home": "JARVIS Chat",
}


HELP = (
    "JARVIS commands (no extra dashboard needed):\n"
    "/help — list commands\n"
    "/island — open the floating Dynamic Island\n"
    "/settings — configure keys, microphone, saved projects and permissions\n"
    "/projects — list your saved coding projects\n"
    "/editors — list detected development editors\n"
    "/draft GOAL — request a Python code draft (provider approval required)\n"
    "/project add — register a project folder in Settings\n"
    "/project NAME — show a saved project's status\n"
    "/project NAME open — open in its configured editor (approval required)\n"
    "/project NAME test — run configured tests (approval required)\n"
    "/project NAME fix GOAL — prepare reviewed code changes in an isolated worktree\n"
    "/code, /pc, /voice, /mobile, /memory, /providers — open the existing tool\n"
    "/review, /tasks, /workflows, /history, /video, /business — open other tools\n"
    "/new — start a fresh conversation. /home — return to Chat.\n"
    "Natural Tamil, Tanglish and English requests still work where supported.\n"
    "Commands do not bypass approvals, enable remote control or execute a shell."
)


def parse_command(text, projects=()):
    """Recognize explicit commands; leave ordinary conversation untouched.

    Unknown slash commands are rejected locally so they are not accidentally
    forwarded to a paid cloud provider. Only saved project names are accepted.
    """
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None
    common = raw.casefold()
    if common in ("settings", "open settings", "setting", "settings திற",
                  "island", "island mode", "eyeland"):
        return Command("island" if common in ("island", "island mode", "eyeland")
                       else "page", target="" if common in ("island", "island mode", "eyeland")
                       else "Settings & Safety")
    if not raw.startswith("/"):
        return None
    keyword, _, remainder = raw.partition(" ")
    keyword = keyword.casefold()
    remainder = remainder.strip()
    # Preserve existing local status/time/capability and video-plan commands.
    # They already have their own guarded handlers in the main assistant.
    if (keyword in ("/status", "/time", "/capabilities") and not remainder or
            keyword == "/video" and remainder):
        return None
    if keyword in ("/help", "/commands", "/developer", "/dev") and not remainder:
        return Command("help")
    if keyword in ("/island", "/eyeland") and not remainder:
        return Command("island")
    if keyword in ("/projects",) and not remainder:
        return Command("projects")
    if keyword == "/editors" and not remainder:
        return Command("editors")
    if keyword == "/draft":
        return Command("code_draft", detail=remainder) if remainder else Command(
            "error", detail="Enter a coding goal: /draft GOAL")
    if keyword == "/new" and not remainder:
        return Command("new")
    if keyword in ("/project", "/projects"):
        if not remainder or remainder.casefold() in ("help", "list"):
            return Command("projects")
        if remainder.casefold() == "add":
            return Command("project_add")
        # A saved project name can contain spaces, so prefer the longest.
        names = sorted((p.name for p in projects if getattr(p, "name", "")),
                       key=len, reverse=True)
        for name in names:
            if not remainder.casefold().startswith(name.casefold()):
                continue
            tail = remainder[len(name):]
            if tail and not tail[0].isspace():
                continue
            instruction = tail.strip()
            verb = instruction.casefold()
            if verb in ("", "status"):
                return Command("project_status", target=name)
            if verb in ("open", "launch"):
                return Command("project_open", target=name)
            if verb in ("test", "tests", "run tests"):
                return Command("project_test", target=name)
            if verb.startswith("fix ") or verb.startswith("change "):
                goal = instruction.split(None, 1)[1].strip()
                if goal:
                    return Command("project_fix", target=name, detail=goal)
            return Command("error", detail="Choose open, test or fix GOAL for that project.")
        return Command("error", detail="Save that project once in Settings using /project add.")
    if keyword[1:] in PAGE_COMMANDS and not remainder:
        return Command("page", target=PAGE_COMMANDS[keyword[1:]])
    return Command("error", detail="Unknown command. Type /help for safe, supported commands.")
