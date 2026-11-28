"""Owner-operated browser actions in a dedicated, visible browser profile."""
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import mimetypes
from pathlib import Path
import json
import shutil
import sys
from urllib.parse import urlencode, urlsplit

from playwright.async_api import async_playwright

MAX_ASSET_BYTES = 25_000_000


class BrowserTaskError(ValueError):
    pass


def origin(url):
    try:
        parts = urlsplit(url)
        port = parts.port
        hostname = parts.hostname
        if parts.scheme == 'https' and hostname and not parts.username and not parts.password and not any(
                c.isspace() or c in '\\\x00' for c in url):
            host = f'[{hostname}]' if ':' in hostname else hostname
            return 'https://' + host + (f':{port}' if port and port != 443 else '')
    except ValueError:
        pass
    raise BrowserTaskError('Choose a full HTTPS address without embedded credentials.')


@dataclass(frozen=True)
class BrowserAction:
    verb: str
    target: str = ''
    value: str = ''
    asset_hash: str = ''

    def digest(self, document):
        payload = json.dumps([document, self.verb, self.target, self.value, self.asset_hash],
                             ensure_ascii=False)
        return sha256(payload.encode()).hexdigest()


HELP = ('/browser search Keywords  ·  /browser open https://…  ·  /browser inspect  ·  /browser fill Field label  ·  '
        '/browser click Button name  ·  /browser link Link name  ·  /browser upload File label  ·  '
        '/browser verify Visible text  ·  /browser close')


def parse_browser(text):
    verb, _, target = text.strip().partition(' ')
    verb, target = verb.lower(), target.strip()
    if verb == 'search' and target:
        if len(target) > 240:
            raise BrowserTaskError('Use at most 240 characters in a search.')
        return BrowserAction('open', 'https://www.google.com/search?' + urlencode({'q': target}))
    if verb in ('inspect', 'close') and not target:
        return BrowserAction(verb)
    if verb in ('open', 'click', 'link', 'fill', 'upload', 'verify') and target:
        if len(target) > (2048 if verb == 'open' else 240):
            raise BrowserTaskError('The browser action is too long.')
        if verb == 'open':
            origin(target)
        return BrowserAction(verb, target)
    raise BrowserTaskError(HELP)


def system_browser():
    if sys.platform == 'win32':
        return {'channel': 'msedge'}
    path = shutil.which('chromium') or shutil.which('google-chrome')
    if not path:
        raise BrowserTaskError('Install Edge for Windows or Chromium to use browser actions.')
    return {'executable_path': path}


class BrowserSession:
    def __init__(self, profile, *, headless=False):
        self.profile = str(Path(profile))
        self.headless = headless
        self.driver = self.context = self.page = None
        self.allowed = ''
        self.revision = 0

    def navigated(self, frame):
        if self.page and frame == self.page.main_frame:
            self.revision += 1

    def context_closed(self, context):
        if self.context == context:
            self.context = self.page = None
            self.revision += 1

    def document(self):
        if not self.page or self.page.is_closed():
            raise BrowserTaskError('Open the authorized website first.')
        current = origin(self.page.url)
        if current != self.allowed:
            raise BrowserTaskError('The browser is on a different origin. Finish signing in manually or authorize that site explicitly.')
        return (current, self.revision, sha256(self.page.url.encode()).hexdigest())

    async def start(self):
        if self.driver is None:
            self.driver = await async_playwright().start()
        if self.context is None:
            self.context = await self.driver.chromium.launch_persistent_context(
                self.profile, headless=self.headless, accept_downloads=False, timeout=15000,
                **system_browser())
            self.context.on('close', self.context_closed)
            self.context.set_default_timeout(4500)
        if self.page is None or self.page.is_closed():
            self.page = next((p for p in self.context.pages if not p.is_closed()), None)
            if self.page is None:
                self.page = await self.context.new_page()
            self.page.on('framenavigated', self.navigated)

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self.driver:
                await self.driver.stop()
            self.driver = self.context = self.page = None
            self.allowed = ''
            self.revision += 1

    async def perform(self, action, document, check):
        check()
        if action.verb == 'open':
            self.allowed = origin(action.target)
            await self.start()
            check()
            response = await self.page.goto(action.target, wait_until='domcontentloaded', timeout=15000)
            check()
            if not response or not response.ok:
                raise BrowserTaskError('The site did not return a successful document.')
            doc = self.document()
            return ('verified', f'Loaded {doc[0]} · HTTP {response.status}', doc)
        current = self.document()
        # Inspect also refreshes the approval context after manual navigation.
        if action.verb == 'inspect':
            data = await self.page.evaluate("""() => ({
                title: document.title.slice(0, 140),
                controls: Array.from(document.querySelectorAll('button,a[href],input,textarea,[role=button]'))
                  .filter(e => e.getClientRects().length && e.type !== 'password')
                  .slice(0, 80).map(e => (e.getAttribute('aria-label') || e.labels?.[0]?.innerText ||
                      e.innerText || e.getAttribute('placeholder') || '').trim().slice(0, 90))
                  .filter(Boolean)
            })""")
            check()
            if self.document() != current:
                raise BrowserTaskError('The page changed during inspection. Inspect again.')
            return ('observed', data['title'] + '\n' + '\n'.join(data['controls']), current)
        if not document or current != tuple(document):
            raise BrowserTaskError('The page changed after review. Inspect it before approving a new action.')
        page = self.page
        if action.verb == 'verify':
            node = page.get_by_text(action.target, exact=True)
            if await node.count() != 1 or not await node.is_visible() or self.document() != current:
                raise BrowserTaskError('The requested text was not uniquely visible.')
            return ('verified', 'Observed the requested text on the approved page.', current)
        locator = (page.get_by_role('button' if action.verb == 'click' else 'link',
                                    name=action.target, exact=True)
                   if action.verb in ('click', 'link') else page.get_by_label(action.target, exact=True))
        if await locator.count() != 1:
            raise BrowserTaskError('Choose a unique accessible name from the page.')
        # Pin the element. A navigation or rerender must never retarget an approval.
        element = await locator.element_handle(timeout=2500)
        if not element or not await element.is_visible() or self.document() != current:
            raise BrowserTaskError('The reviewed control changed. Inspect the page again.')
        check()
        if action.verb in ('click', 'link'):
            await element.click(timeout=4500)
            try:
                next_doc = self.document()
            except BrowserTaskError:
                next_doc = None
            return ('dispatched', 'Click delivered. Verify the resulting page or receipt.', next_doc)
        if action.verb == 'fill':
            allowed = await element.evaluate("""e => (e.tagName === 'TEXTAREA' ||
              (e.tagName === 'INPUT' && ['text','search','url','email','tel'].includes(e.type))) &&
              !/password|cc-|one-time-code/i.test(e.autocomplete || '')""")
            if not allowed:
                raise BrowserTaskError('Choose a regular draft text field. Enter credentials and payment details manually.')
            check()
            await element.fill(action.value, timeout=4500)
            if await element.input_value() != action.value:
                raise BrowserTaskError('The text field did not retain the requested value.')
            evidence = 'The field contains the requested text.'
        elif action.verb == 'upload':
            if not await element.evaluate("e => e.tagName === 'INPUT' && e.type === 'file'"):
                raise BrowserTaskError('Choose a labelled file input.')
            path = Path(action.value)
            contents = await asyncio.to_thread(read_asset, path)
            if sha256(contents).hexdigest() != action.asset_hash:
                raise BrowserTaskError('The file changed after selection. Choose it again.')
            check()
            if self.document() != current:
                raise BrowserTaskError('The page changed while verifying the file.')
            await element.set_input_files(
                {'name': path.name, 'mimeType': mimetypes.guess_type(path)[0] or 'application/octet-stream',
                 'buffer': contents},
                timeout=4500)
            chosen = await element.evaluate('e => Array.from(e.files, f => [f.name, f.size])')
            if chosen != [[path.name, len(contents)]]:
                raise BrowserTaskError('The selected file could not be verified.')
            evidence = 'The file input contains the selected name and byte size. Server acceptance is unknown.'
        else:
            raise BrowserTaskError('Unknown browser action.')
        if self.document() != current:
            raise BrowserTaskError('The page changed before the result was verified.')
        return ('verified', evidence, current)


def read_asset(path):
    try:
        if path.is_symlink() or not path.is_file():
            raise BrowserTaskError('The selected file is no longer available.')
        with path.open('rb') as stream:
            contents = stream.read(MAX_ASSET_BYTES + 1)
    except OSError:
        raise BrowserTaskError('The selected file could not be read.') from None
    if len(contents) > MAX_ASSET_BYTES:
        raise BrowserTaskError('Select an asset no larger than 25 MB.')
    return contents
