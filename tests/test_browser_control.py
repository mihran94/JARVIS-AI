import asyncio
from hashlib import sha256
import os
import shutil
import sys

import pytest

from automation.browser import BrowserAction, BrowserSession, BrowserTaskError, parse_browser
from security.policy import Policy


def test_browser_command_requires_an_https_destination():
    assert parse_browser('open https://example.com').target == 'https://example.com'
    with pytest.raises(BrowserTaskError):
        parse_browser('open http://example.com')


def test_upload_approval_binds_selected_bytes():
    one = BrowserAction('upload', 'Asset', '/tmp/asset.txt', 'hash-one')
    two = BrowserAction('upload', 'Asset', '/tmp/asset.txt', 'hash-two')
    assert one.digest(('https://example.com', 1, 'document')) != two.digest(
        ('https://example.com', 1, 'document'))


def test_browser_actions_against_a_real_document(tmp_path):
    on_windows_ci = sys.platform == 'win32' and os.environ.get('GITHUB_ACTIONS') == 'true'
    if not on_windows_ci and os.environ.get('JARVIS_BROWSER_ACCEPTANCE') != '1':
        pytest.skip('Run explicitly on a machine that can launch a real browser.')
    if sys.platform != 'win32' and not (shutil.which('chromium') or shutil.which('google-chrome')):
        pytest.skip('System Chromium or Chrome is required for this browser integration test.')

    async def run():
        session = BrowserSession(tmp_path / 'profile', headless=True)
        policy = Policy()
        ticket = policy.ticket()

        def check():
            policy.check(ticket)

        try:
            await session.start()
            await session.page.route('https://example.com/**', lambda route: route.fulfill(
                content_type='text/html',
                body="""<label>Draft<input></label><label>Asset<input type="file"></label>
                <button onclick="document.querySelector('p').textContent='Saved locally'">Save</button>
                <p>Ready</p>"""))
            status, _, doc = await session.perform(parse_browser('open https://example.com/test'), None, check)
            assert status == 'verified'
            status, contents, inspected = await session.perform(BrowserAction('inspect'), None, check)
            assert status == 'observed' and 'Draft' in contents and inspected == doc
            draft = BrowserAction('fill', 'Draft', 'வணக்கம்')
            assert (await session.perform(draft, doc, check))[0] == 'verified'
            assert await session.page.get_by_label('Draft').input_value() == 'வணக்கம்'
            path = tmp_path / 'asset.txt'
            path.write_bytes(b'sample')
            upload = BrowserAction('upload', 'Asset', str(path), sha256(b'sample').hexdigest())
            assert (await session.perform(upload, doc, check))[0] == 'verified'
            path.write_bytes(b'edited')
            with pytest.raises(BrowserTaskError, match='file changed'):
                await session.perform(upload, doc, check)
            assert (await session.perform(BrowserAction('click', 'Save'), doc, check))[0] == 'dispatched'
            assert (await session.perform(BrowserAction('verify', 'Saved locally'), doc, check))[0] == 'verified'
            await session.page.reload()
            with pytest.raises(BrowserTaskError, match='page changed'):
                await session.perform(BrowserAction('click', 'Save'), doc, check)
        finally:
            await session.close()

    asyncio.run(run())
