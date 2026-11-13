"""Strictly local voice-intent parser; no arbitrary commands or shell execution."""
import re

COMMANDS = {
    "open notepad": "Notepad",
    "launch notepad": "Notepad",
    "start notepad": "Notepad",
    "open calculator": "Calculator",
    "launch calculator": "Calculator",
    "start calculator": "Calculator",
}


def parse_voice_command(text):
    """Return allowlisted app name or None; require a complete utterance match."""
    if not isinstance(text, str):
        return None
    normalized = re.sub(r"\s+", " ", text.casefold()).strip(" .!?")
    return COMMANDS.get(normalized)
