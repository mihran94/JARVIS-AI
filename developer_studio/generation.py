"""Single-file Python drafting; model output never grants execution permission."""
import ast


def messages_for_goal(goal):
    goal = goal.strip()
    if not goal or len(goal) > 20000:
        raise ValueError('Describe the coding task in 1 to 20,000 characters.')
    return [
        {'role': 'system', 'content':
         'Create a single Python 3.12 source file for the user task. Return only source code, '
         'without Markdown fences. Prefer the standard library. Include useful comments and '
         'a main guard. Never claim you ran or tested the code. Do not include credentials.'},
        {'role': 'user', 'content': goal},
    ]


def prepare_draft(text):
    text = text.strip()
    if text.startswith('```python\n') or text.startswith('```\n'):
        lines = text.splitlines()
        if lines[-1] == '```':
            text = '\n'.join(lines[1:-1])
    if not text or len(text.encode('utf-8')) > 200000:
        raise ValueError('Empty or oversized code draft.')
    try:
        ast.parse(text)
    except (SyntaxError, ValueError):
        return text, 'Draft needs correction: Python syntax check failed. Nothing was executed.'
    return text, 'Python syntax passed. Behavior and safety are unverified; nothing was executed.'
