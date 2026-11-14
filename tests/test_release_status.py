import json
import pytest
from core.release_status import parse_releases, ReleaseMetadataError, MAX_METADATA_BYTES


def sample(tag='v0.4.0', url='https://github.com/mihran94/JARVIS-AI/releases/tag/v0.4.0'):
    return {'tag_name': tag, 'html_url': url, 'draft': False, 'prerelease': False}


def test_absent_release_is_not_mistaken_for_update():
    assert parse_releases(b'[]') is None


def test_valid_release_and_prerelease():
    assert parse_releases(json.dumps([sample()]).encode()) == {
        'tag': 'v0.4.0', 'url': sample()['html_url'], 'prerelease': False}
    data = sample(tag='v1.0.0-beta/1',
                  url='https://github.com/mihran94/JARVIS-AI/releases/tag/v1.0.0-beta%2F1')
    data['prerelease'] = True
    assert parse_releases(json.dumps([data]).encode())['prerelease'] is True


def test_drafts_are_not_published():
    a = sample(); a['draft'] = True
    assert parse_releases(json.dumps([a]).encode()) is None


@pytest.mark.parametrize('payload', [
    b'{}', b'{broken', b'"oops"', json.dumps([123]).encode(),
    json.dumps([sample(url='http://github.com/mihran94/JARVIS-AI/releases/tag/v0.4.0')]).encode(),
    json.dumps([sample(url='https://github.com.evil.test/mihran94/JARVIS-AI/releases/tag/v0.4.0')]).encode(),
    json.dumps([sample(url='https://github.com/attacker/repo/releases/tag/v0.4.0')]).encode(),
    json.dumps([sample(tag='../evil')]).encode(), b'x' * (MAX_METADATA_BYTES+1),
])
def test_reject_untrusted_metadata(payload):
    with pytest.raises(ReleaseMetadataError): parse_releases(payload)
