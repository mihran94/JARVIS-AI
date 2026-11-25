import asyncio
from types import SimpleNamespace

import pytest

from integrations.mark.jarvis_spoken import dispatch_spoken, parse_spoken


@pytest.mark.parametrize(('text', 'expected'), [
    ('JARVIS M, என்னோட saved projects list காட்டு', {'operation': 'projects'}),
    ('ஜார்விஸ், என்னுடைய ப்ராஜெக்ட்ஸ் பட்டியல் காட்டு', {'operation': 'projects'}),
    ('ஜார்விஸ், என்னோட சேவ்டு ப்ராஜெக்ட்ஸ் லிஸ்ட் காட்டு', {'operation': 'projects'}),
    ('JARVIS PC plugin-la saved projects list kaattu', {'operation': 'projects'}),
    ('JARVIS PC plugin use panni Calculator-la 17 times 23 calculate pannu',
     {'operation': 'calculate', 'value': '17 * 23'}),
    ('கால்குலேட்டரில் பதினேழு பெருக்கல் இருபத்து மூன்று கணக்கு போடு',
     {'operation': 'calculate', 'value': '17 * 23'}),
    ('quote calculator 17 times 23 to me', None),
    ('17 times 23', None),
    ('what is the calculator workflow?', None),
])
def test_complete_spoken_commands(text, expected):
    assert parse_spoken(text) == expected


def test_completed_voice_turn_uses_native_plugin_and_asks_on_hud():
    activity = []
    mark = SimpleNamespace(
        ui=SimpleNamespace(muted=False, write_log=activity.append),
        _plugin_registry=SimpleNamespace(run=lambda name, args, ui:
                                         activity.append((name, args)) or '[CONFIRMATION_PENDING]'),
        speak=activity.append,
    )
    asyncio.run(dispatch_spoken(mark, 'Calculator-la 17 times 23 calculate pannu'))
    assert activity[0] == ('jarvis_pc_projects', {'operation': 'calculate', 'value': '17 * 23'})
    assert 'approval on the HUD' in activity[1]
    assert 'Confirm' in activity[2]
