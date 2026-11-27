"""App data and credential scope for an explicitly selected development profile."""
import os
from pathlib import Path
import re

RESTART_EXIT_CODE = 75
APP_NAME = 'JARVIS M'
APP_VERSION = '0.3.0'
DATA_FOLDER = 'JarvisM'


def restart_supported():
    """Only the launcher can replace a session after its process exits."""
    return os.environ.get('JARVIS_RESTART_MANAGED') == '1'


def reviewed_update_restart_supported():
    return restart_supported() and (
        not development_profile() or os.environ.get('JARVIS_RESTART_REVIEWED_DEV') == '1')


def development_profile():
    value = os.environ.get('JARVIS_DEVELOPMENT_PROFILE', '')
    return value if re.fullmatch(r'[a-f0-9]{24}', value) else ''


def data_directory():
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    profile = development_profile()
    if profile:
        return local / (DATA_FOLDER + '-Development') / profile
    return local / DATA_FOLDER
