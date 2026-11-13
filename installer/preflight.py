"""Static preflight for the JARVIS BLUE Windows packaging workflow.

Checks source syntax and critical imports without opening the GUI, running
automation, making network calls, or reading user credentials.
"""
from pathlib import Path
import ast
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("desktop", "core", "providers", "security", "automation",
               "agents", "developer_studio", "scripts")
REQUIRED = ("main.py", "desktop/app.py", "requirements.txt",
            "installer/jarvis-blue.iss")

def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        print("Missing required source files:", ", ".join(missing))
        return 1

    sources = [ROOT / "main.py", ROOT / "installer" / "preflight.py"]
    if (ROOT / "tests").exists():
        sources.extend((ROOT / "tests").rglob("test_*.py"))
    for folder in SOURCE_DIRS:
        directory = ROOT / folder
        if directory.exists():
            sources.extend(directory.rglob("*.py"))

    errors = []
    for path in sources:
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for module in ("PySide6", "httpx", "keyring", "psutil", "pyttsx3", "vosk", "sounddevice"):
        if importlib.util.find_spec(module) is None:
            errors.append(f"Missing installed Python module: {module}")

    if errors:
        print("Preflight FAILED:")
        for error in errors:
            print(" -", error)
        return 1
    print(f"Preflight PASSED: {len(sources)} Python source files parsed; core packages present.")
    print("This does not verify GUI startup, Windows automation, API calls, or installer behavior.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
