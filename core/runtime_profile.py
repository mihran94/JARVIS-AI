"""App data and credential scope for an explicitly selected development profile."""
import os
from pathlib import Path
import re


def development_profile():
    value = os.environ.get('JARVIS_DEVELOPMENT_PROFILE', '')
    return value if re.fullmatch(r'[a-f0-9]{24}', value) else ''


def data_directory():
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    profile = development_profile()
    if profile:
        return local / 'JarvisAI-Development' / profile
    return local / 'JarvisAI'
