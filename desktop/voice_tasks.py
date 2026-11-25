"""Interpret only complete, explicit local requests from live transcripts."""
import re

from automation.desktop_tasks import DesktopTask, parse_desktop_task
from core.conversation import addressed_request
from desktop.voice_commands import parse_voice_command
from developer_studio.commands import parse_command


PROJECT_LIST = {
    'list my saved projects', 'list saved projects', 'show saved projects', 'show my projects',
    'projects list kaattu', 'saved projects list kaattu', 'ennoda projects kattu',
    'என்னோட சேவ்டு ப்ராஜெக்ட்ஸ் லிஸ்ட் காட்டு', 'என்னோட saved projects list காட்டு',
    'சேமித்த திட்டங்களைக் காட்டு', 'சேமித்த திட்டங்கள் காட்டு', 'என்னுடைய projects காட்டு',
}
MATH_VERBS = {
    '+': '+', 'plus': '+', 'பிளஸ்': '+', 'கூட்டல்': '+',
    '-': '-', '−': '-', 'minus': '-', 'மைனஸ்': '-', 'கழித்தல்': '-',
    '*': '*', '×': '*', 'times': '*', 'into': '*', 'இன்டு': '*', 'பெருக்கல்': '*',
}
WORD_VALUES = {
    word: number for words in (
        'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen '
        'fifteen sixteen seventeen eighteen nineteen',
        'பூஜ்யம் ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து பதினொன்று '
        'பன்னிரண்டு பதின்மூன்று பதினான்கு பதினைந்து பதினாறு பதினேழு பதினெட்டு பத்தொன்பது',
    ) for number, word in enumerate(words.split())
}
TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
        'seventy': 70, 'eighty': 80, 'ninety': 90, 'இருபத்து': 20, 'முப்பத்து': 30}
OPERATOR_PATTERN = '|'.join(re.escape(word) for word in MATH_VERBS)
MATH = re.compile(
    r'^(?:calculate|calculator(?:[- ](?:la|ல))?|கால்குலேட்ட(?:ர்(?:லே?)?|ரில்)|கணக்கிடு)'
    r'[\s:,.]+(?P<left>.+?)\s*(?P<op>' + OPERATOR_PATTERN + r')\s*(?P<right>.+?)'
    r'(?:\s+(?:calculate pannu|கணக்கு போடு|கணக்கிடு|எவ்வளவு))?$',
)


def number(value):
    value = value.strip()
    if not value:
        return None
    if re.fullmatch(r'\d{1,6}', value):
        return int(value)
    if value in WORD_VALUES:
        return WORD_VALUES[value]
    first, *rest = value.replace('-', ' ').split()
    if first in TENS:
        if not rest:
            return TENS[first]
        if len(rest) == 1 and 0 < WORD_VALUES.get(rest[0], -1) < 10:
            return TENS[first] + WORD_VALUES[rest[0]]
    return None


def local_voice_request(transcript, projects=()):
    """Return an existing approval or project route, or leave the speech as chat."""
    if not isinstance(transcript, str) or len(transcript) > 2400:
        return None
    transcript = re.sub(r'^\s*(?:hey\s+)?jarvis\s+m(?=[\s,.:!]|$)[\s,.:!]*',
                        '', transcript, flags=re.IGNORECASE)
    text = addressed_request(transcript)
    normalized = ' '.join(text.casefold().split()).strip(' .,! ?।')
    if normalized in PROJECT_LIST:
        return 'project', '/projects'
    project_command = text if normalized.startswith('/project') else '/' + text
    if normalized.startswith(('project ', '/project ')):
        command = parse_command(project_command, projects)
        if command is not None and command.kind in ('project_status', 'project_open', 'project_test'):
            return 'project', project_command
    try:
        task = parse_desktop_task(text)
    except ValueError:
        return None
    if task is not None:
        return 'desktop', task
    expression = MATH.fullmatch(normalized)
    if expression:
        left, right = (number(expression[field]) for field in ('left', 'right'))
        if left is not None and right is not None:
            return 'desktop', DesktopTask('Calculator', f'{left} {MATH_VERBS[expression["op"]]} {right}', True)
    app = parse_voice_command(text)
    if app:
        return 'launch', app
    return None
