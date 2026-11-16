"""AI Studio Build link and reviewable update prompts for the business site."""
import re
from urllib.parse import urlsplit


STUDIO_NAME = 'AI Creative Studio'
STUDIO_ID = 'bb4d1772-83ae-481c-a041-1436f9b732ab'
STUDIO_URL = f'https://ai.studio/apps/{STUDIO_ID}'
APP_PATH = re.compile(r'/apps/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/?')


def validate_studio_url(value):
    value = value.strip()
    parts = urlsplit(value)
    if (parts.scheme != 'https' or parts.netloc not in ('ai.studio', 'aistudio.google.com')
            or not APP_PATH.fullmatch(parts.path) or any(char.isspace() for char in value)):
        raise ValueError('Enter an HTTPS Google AI Studio Build project link.')
    return value


def studio_update_prompt(brief, project_url=STUDIO_URL):
    project_url = validate_studio_url(project_url)
    brief = brief.strip()
    if not 1 <= len(brief) <= 12_000:
        raise ValueError('Enter a website update brief with 1–12,000 characters.')

    uploaded_project = urlsplit(project_url).path.rstrip('/').endswith('/' + STUDIO_ID)
    name = STUDIO_NAME if uploaded_project else 'the linked website'
    context = (
        'The uploaded snapshot is a React/TypeScript site with an Express backend. '
        'Inspect src/App.tsx, the relevant src/components and src/lib modules, and server.ts '
        'when the change affects server behavior.'
        if uploaded_project else
        'Inspect the project in Build mode and locate the relevant pages and server routes first.'
    )
    return (
        f'Update {name} in its existing Google AI Studio Build project.\n'
        f'Project: {project_url}\n\n'
        f'Requested update:\n{brief}\n\n'
        f'{context}\n'
        'Keep changes scoped to the request. Preserve the existing design system, translations, '
        'order and quote flows, account permissions, and payment behavior outside that scope. '
        'Keep API keys server-side and use test data when verifying changes.\n'
        'Preview desktop and mobile layouts. Run the relevant tests and summarize changed files, '
        'verification results and any follow-up needed. Leave the preview ready for review.'
    )
