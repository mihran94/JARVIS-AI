"""Apply a narrow, reviewable homepage-copy patch to an AI Studio export."""
from ast import literal_eval
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


TRANSLATIONS = 'src/lib/translations.ts'
HERO = 'src/components/Hero.tsx'
LANGUAGES = {'en': 'English', 'fr': 'Français', 'ta': 'தமிழ்'}
EDITABLE = {
    'heroBadge': 100, 'heroHeading': 150, 'heroSubheading': 340,
    'btnStartProject': 55, 'btnExploreServices': 55, 'btnViewWork': 55,
}
SOURCE_LIMIT = 512_000
ZIP_LIMIT = 150_000_000
LANGUAGE_BLOCK = r'(?ms)^  {language}: \{{\r?\n(?P<body>.*?)^  \}},?\r?$'
QUOTED = r"""(?:'(?:[^'\\\r\n]|\\.)*'|"(?:[^"\\\r\n]|\\.)*")"""
OLD_HEADING = re.compile(
    r"Turn Your Vision Into\{' '\}\s*<span className=\"(?P<style>[^\"]+)\">"
    r"\s*Stunning Digital Content\.\s*</span>"
)


def copy_matches(source, language):
    if language not in LANGUAGES:
        raise ValueError('Choose a supported website language.')
    block = re.search(LANGUAGE_BLOCK.format(language=language), source)
    if not block:
        raise ValueError('The export is missing the selected language.')
    matches = {}
    for field in EDITABLE:
        pattern = rf'(?m)^    {field}: (?P<value>{QUOTED}),?\r?$'
        match = re.search(pattern, block['body'])
        if not match:
            raise ValueError(f'The website export is missing {field}.')
        matches[field] = (
            block.start('body') + match.start('value'),
            block.start('body') + match.end('value'),
            literal_eval(match['value']),
        )
    return matches


def safe_members(archive):
    seen = set()
    total = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        parts = path.parts
        if (not parts or path.is_absolute() or '..' in parts or '\\' in info.filename
                or any(':' in part for part in parts)
                or stat.S_ISLNK(info.external_attr >> 16)
                or path.as_posix().casefold() in seen):
            raise ValueError('The website ZIP contains an unsafe or duplicate path.')
        seen.add(path.as_posix().casefold())
        total += info.file_size
        if total > ZIP_LIMIT:
            raise ValueError('The website ZIP exceeds the supported size.')
        yield info


@dataclass(frozen=True)
class WebsiteExport:
    path: Path
    language: str
    translations: str
    hero: str

    @classmethod
    def load(cls, path, language):
        path = Path(path).resolve()
        try:
            with ZipFile(path) as archive:
                if any(archive.getinfo(name).file_size > SOURCE_LIMIT for name in (TRANSLATIONS, HERO)):
                    raise ValueError('The homepage source is too large.')
                translations = archive.read(TRANSLATIONS).decode('utf-8')
                hero = archive.read(HERO).decode('utf-8')
        except (OSError, BadZipFile, KeyError, UnicodeError) as error:
            raise ValueError('Select the AI Creative Studio source ZIP from Google AI Studio.') from error
        website = cls(path, language, translations, hero)
        website.current_copy()
        return website

    def current_copy(self):
        return {field: value for field, (_, _, value) in copy_matches(self.translations, self.language).items()}

    def messages(self, brief):
        brief = brief.strip()
        if not 1 <= len(brief) <= 12_000:
            raise ValueError('Enter a homepage copy brief with 1–12,000 characters.')
        return [
            {'role': 'system', 'content': (
                f'Edit the AI Creative Studio homepage in {LANGUAGES[self.language]}. '
                'Return only a JSON object of changed keys and plain-text values. '
                f'These are the allowed keys and maximum lengths: {json.dumps(EDITABLE)}. '
                'Write only copy changes supported by the request. Do not invent prices, guarantees, '
                'client counts, credentials, or business policies. Return {} if the change is outside homepage copy.'
            )},
            {'role': 'user', 'content': json.dumps(
                {'request': brief, 'current_copy': self.current_copy()}, ensure_ascii=False)},
        ]

    def draft(self, response):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', response.strip(), flags=re.I)
        try:
            candidate = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError('Gemini did not return a valid homepage copy draft.') from error
        current = self.current_copy()
        if not isinstance(candidate, dict) or candidate.keys() - EDITABLE.keys():
            raise ValueError('Gemini proposed fields outside the supported homepage copy.')
        changes = {}
        for field, value in candidate.items():
            if (not isinstance(value, str) or not 1 <= len(value.strip()) <= EDITABLE[field]
                    or any(ord(char) < 32 for char in value)):
                raise ValueError(f'The proposed {field} must be short, single-line text.')
            if value.strip() != current[field]:
                changes[field] = value.strip()
        if not changes:
            raise ValueError('No homepage copy changes match the request. Try a headline, subtitle, badge or button label.')
        return SiteDraft(self, current, changes)


@dataclass(frozen=True)
class SiteDraft:
    website: WebsiteExport
    before: dict
    changes: dict

    def updated_files(self):
        translations = self.website.translations
        matches = copy_matches(translations, self.website.language)
        for field in sorted(self.changes, key=lambda key: matches[key][0], reverse=True):
            start, end, _ = matches[field]
            translations = translations[:start] + json.dumps(self.changes[field], ensure_ascii=False) + translations[end:]
        files = {TRANSLATIONS: translations.encode('utf-8')}
        if 'heroHeading' in self.changes and '{t.heroHeading}' not in self.website.hero:
            hero, replaced = OLD_HEADING.subn(
                lambda m: f'<span className="{m["style"]}">{{t.heroHeading}}</span>', self.website.hero, count=1)
            if replaced != 1:
                raise ValueError('This website export uses a different headline layout.')
            files[HERO] = hero.encode('utf-8')
        return files

    def export_zip(self, destination):
        source = self.website.path
        destination = Path(destination).resolve()
        if destination == source or (destination.exists() and destination.samefile(source)):
            raise ValueError('Save the website draft as a separate ZIP.')
        files = self.updated_files()
        # Validate the same source version before packaging the draft.
        with ZipFile(source) as incoming:
            if (incoming.read(TRANSLATIONS) != self.website.translations.encode('utf-8')
                    or incoming.read(HERO) != self.website.hero.encode('utf-8')):
                raise ValueError('The homepage source ZIP changed. Create a new draft first.')
            members = list(safe_members(incoming))
            with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
                pending = Path(temporary.name)
            try:
                with ZipFile(pending, 'w', ZIP_DEFLATED) as outgoing:
                    for info in members:
                        content = files[info.filename] if info.filename in files else incoming.read(info)
                        outgoing.writestr(info, content, compress_type=ZIP_DEFLATED)
                os.replace(pending, destination)
            finally:
                pending.unlink(missing_ok=True)

    def preview_html(self, label='Homepage copy preview'):
        def hero(values):
            badge, heading, description, primary, services, portfolio = (
                escape(values[field]) for field in EDITABLE
            )
            return (
                f'<section class="hero"><span class="badge">{badge}</span><h1>{heading}</h1>'
                f'<p>{description}</p><div class="buttons"><span class="primary">{primary} ↗</span>'
                f'<span>{services}</span><span>{portfolio}</span></div></section>'
            )

        before = dict(self.before)
        original_heading = OLD_HEADING.search(self.website.hero)
        if original_heading:
            before['heroHeading'] = 'Turn Your Vision Into Stunning Digital Content.'
        return f"""<!doctype html>
<html lang="{self.website.language}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Creative Studio · {escape(label)}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#070913;color:#e2e8f0;font:16px "Space Grotesk","Segoe UI",sans-serif}}
main{{max-width:1410px;margin:auto;padding:clamp(20px,3.5vw,52px)}}
header{{display:flex;justify-content:space-between;align-items:center;gap:18px;padding-bottom:24px;
border-bottom:1px solid #282b43}}header strong{{font-size:21px;color:#f8fafc}}header span{{color:#a2acc3}}
section.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-top:26px}}
article{{border:1px solid #30334e;border-radius:18px;overflow:hidden;background:#0d1021}}
article h2{{margin:0;padding:16px 20px;font-size:13px;color:#a9b6d2}}
article.proposed{{border-color:#6254a5}}article.proposed h2{{color:#c8b6ff}}
.hero{{padding:clamp(22px,4vw,62px);text-align:center;min-height:490px;
background:radial-gradient(ellipse at 50% 40%,#30225e 0,#151832 45%,#0a1127 85%)}}
.badge{{display:inline-block;padding:7px 12px;border:1px solid #515880;border-radius:30px;
font-size:12px;color:#c9daf3;background:#1e294c}}
h1{{font-size:clamp(31px,4.1vw,62px);line-height:1.07;margin:25px 0 17px;letter-spacing:-.045em;
color:#e6f6ff;background:linear-gradient(100deg,#70edfc,#b8b3ff,#d8a4fc);
-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;overflow-wrap:anywhere}}
p{{line-height:1.6;color:#c6d1e7;overflow-wrap:anywhere}}
.buttons{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:24px}}
.buttons span{{border:1px solid #47486c;border-radius:10px;padding:10px 13px;background:#202640;font-size:13px}}
.buttons .primary{{background:linear-gradient(110deg,#5846ad,#7436ac,#086581);color:white;border:0;font-weight:700}}
@media(max-width:800px){{section.grid{{grid-template-columns:1fr}}header{{align-items:flex-start;flex-direction:column}}.hero{{min-height:0}}}}
</style></head><body><main>
<header><strong>AI Creative Studio</strong><span>{escape(label)}</span></header>
<section class="grid">
<article><h2>Current copy</h2>{hero(before)}</article>
<article class="proposed"><h2>Proposed copy</h2>{hero(before | self.changes)}</article>
</section></main></body></html>"""
