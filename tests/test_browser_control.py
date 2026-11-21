import asyncio
import os
import shutil
import sys

import pytest
from playwright.async_api import async_playwright

from automation.browser import BrowserAction, BrowserSession, BrowserTaskError, parse_browser


def test_browser_command_requires_an_https_destination():
    assert parse_browser('open https://example.com').target == 'https://example.com'
    with pytest.raises(BrowserTaskError):
        parse_browser('open http://example.com')


def test_browser_actions_against_a_real_document(tmp_path):
    if os.environ.get('JARVIS_BROWSER_ACCEPTANCE') != '1':
        pytest.skip('Run explicitly on a machine that can launch a real browser.')
    chromium = shutil.which('chromium')
    if not chromium and sys.platform != 'win32':
        pytest.skip('System Chromium is required for this browser integration test.')

    async def run():
        async with async_playwright() as playwright:
            options = {'channel': 'msedge'} if sys.platform == 'win32' else {'executable_path': chromium}
            browser = await playwright.chromium.launch(**options)
            try:
                page = await browser.new_page()
                await page.route('https://example.com/**', lambda route: route.fulfill(
                    content_type='text/html',
                    body='''<label>Draft<input></label><label>Asset<input type="file"></label>
                    <button onclick="document.querySelector('p').textContent='Saved locally'">Save</button>
                    <p>Ready</p>'''))
                await page.goto('https://example.com/test')
                session = BrowserSession(tmp_path)
                session.page = page
                session.allowed = 'https://example.com'
                check = lambda: None
                status, contents, doc = await session.perform(BrowserAction('inspect'), None, check)
                assert status == 'observed' and 'Draft' in contents
                for action in (BrowserAction('fill', 'Draft', 'வணக்கம்'),
                               BrowserAction('upload', 'Asset', str(tmp_path / 'asset.txt'))):
                    (tmp_path / 'asset.txt').write_text('sample')
                    assert (await session.perform(action, doc, check))[0] == 'verified'
                assert await page.get_by_label('Draft').input_value() == 'வணக்கம்'
                assert (await session.perform(BrowserAction('click', 'Save'), doc, check))[0] == 'dispatched'
                assert (await session.perform(BrowserAction('verify', 'Saved locally'), doc, check))[0] == 'verified'
                await page.goto('https://example.com/new')
                with pytest.raises(BrowserTaskError, match='changed'):
                    await session.perform(BrowserAction('click', 'Save'), doc, check)
            finally:
                await browser.close()

    asyncio.run(run())
