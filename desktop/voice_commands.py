"""Strictly local voice-intent parser; no arbitrary commands or shell execution."""
import re

from core.conversation import addressed_request

from automation.windows import EDITOR_EXECUTABLES
from video_studio.planning import VIDEO_TOOLS

COMMANDS = {
    "open notepad": "Notepad",
    "launch notepad": "Notepad",
    "start notepad": "Notepad",
    "open calculator": "Calculator",
    "launch calculator": "Calculator",
    "start calculator": "Calculator",
    "நோட்பேட் திற": "Notepad",
    "நோட்பேடை திற": "Notepad",
    "கால்குலேட்டர் திற": "Calculator",
    "கால்குலேட்டரை திற": "Calculator",
}

aliases = {name.casefold(): name for name in (*VIDEO_TOOLS, *EDITOR_EXECUTABLES)}
aliases.update({'notepad': 'Notepad', 'calculator': 'Calculator'})
aliases.update({'flow': 'Google Flow', 'davinci': 'DaVinci Resolve'})
for alias, name in aliases.items():
    COMMANDS.update({
        f'open {alias}': name,
        f'launch {alias}': name,
        f'{alias} திறந்து வை': name,
        f'{alias} open பண்ணு': name,
        f'{alias} open pannu': name,
        f'{alias} திற': name,
    })


def parse_voice_command(text):
    """Return allowlisted app name or None; require a complete utterance match."""
    if not isinstance(text, str):
        return None
    normalized = re.sub(r"\s+", " ", addressed_request(text).casefold()).strip(" .!?।,")
    return COMMANDS.get(normalized)
