import httpx
import pytest

from news.briefing import FEEDS, fetch_headlines, parse_feed, prompt_messages, source_text


RSS = b'''<rss version="2.0"><channel>
<item><title>A sample headline</title><link>https://example.com/story</link></item>
<item><title>A sample headline</title><link>https://example.com/repeat</link></item>
<item><title>Another headline</title><link>javascript:alert(1)</link></item>
</channel></rss>'''


def test_both_feeds_preserve_available_headlines_and_report_partial_failure():
    visited = []

    def respond(request):
        visited.append(str(request.url))
        if str(request.url) == FEEDS['france'][1]:
            return httpx.Response(200, content=RSS)
        return httpx.Response(503)

    rows, missing = fetch_headlines('both', lambda: None, httpx.MockTransport(respond))
    assert visited == [entry[1] for entry in FEEDS.values()]
    assert missing == ['srilanka']
    assert [row.title for row in rows] == ['A sample headline', 'Another headline']
    assert rows[1].url == ''
    report = source_text(rows, missing)
    assert 'https://example.com/story' in report and 'Feed unavailable: Sri Lanka' in report
    assert 'A sample headline' in prompt_messages(rows)[1]['content']


def test_feed_rejects_dtd_and_bounds_headlines():
    with pytest.raises(ValueError):
        parse_feed(b'<!DOCTYPE rss><rss/>', 'france', 'test')
    long_feed = b'<rss><channel>' + b''.join(
        f'<item><title>Story {i}</title></item>'.encode() for i in range(12)
    ) + b'</channel></rss>'
    assert len(parse_feed(long_feed, 'france', 'test')) == 3
