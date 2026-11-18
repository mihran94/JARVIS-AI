"""Web research: the page is read, and the provider answers from it."""
import ipaddress

import pytest

from research.research import (
    Page, ResearchError, build_prompt, check_address, check_url, fetch,
    readable_text, research,
)


class FakeResponse:
    def __init__(self, text='', status_code=200, content=None, encoding='utf-8'):
        self.text = text
        self.status_code = status_code
        self.content = content if content is not None else text.encode('utf-8')
        self.encoding = encoding


class FakeClient:
    """A client that answers without touching the network."""

    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse('<html><body>text</body></html>')
        self.error = error
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        if self.error is not None:
            raise self.error
        return self.response


def a_resolver_that_gives(*addresses):
    def resolver(host, port):
        return [(2, 1, 6, '', (address, 0)) for address in addresses]
    return resolver


def test_only_https_is_read():
    check_url('https://example.com/page')
    with pytest.raises(ResearchError):
        check_url('http://example.com/page')
    with pytest.raises(ResearchError):
        check_url('ftp://example.com')
    with pytest.raises(ResearchError):
        check_url('')


def test_an_address_that_has_no_host_is_refused():
    with pytest.raises(ResearchError):
        check_url('https:///page')


def test_a_private_address_is_refused():
    with pytest.raises(ResearchError):
        check_address('pc.local', a_resolver_that_gives('192.168.1.20'))
    with pytest.raises(ResearchError):
        check_address('pc.local', a_resolver_that_gives('127.0.0.1'))
    with pytest.raises(ResearchError):
        check_address('pc.local', a_resolver_that_gives('169.254.10.1'))
    with pytest.raises(ResearchError):
        check_address('pc.local', a_resolver_that_gives('10.0.0.5'))


def test_a_public_address_is_allowed():
    check_address('example.com', a_resolver_that_gives('93.184.216.34'))


def test_an_address_that_cannot_be_resolved_is_refused():
    def resolver(host, port):
        raise OSError('no such host')
    with pytest.raises(ResearchError):
        check_address('nothing.invalid', resolver)


def test_the_readable_text_of_a_page():
    markup = '''<html><head><title>A page</title><style>p{}</style></head>
    <body><h1>Heading</h1><p>First line.</p><p>Second line.</p>
    <script>alert('x')</script><!-- a comment --></body></html>'''
    title, text = readable_text(markup)
    assert title == 'A page'
    assert 'Heading' in text
    assert 'First line.' in text
    assert 'Second line.' in text
    assert 'alert' not in text
    assert 'a comment' not in text


def test_a_page_is_read():
    client = FakeClient(FakeResponse(
        '<html><head><title>Docs</title></head><body><p>The answer is 42.</p></body></html>'))
    page = fetch('https://example.com/docs', client=client, allow_private=True)
    assert page.title == 'Docs'
    assert 'The answer is 42.' in page.text
    assert client.requested == ['https://example.com/docs']


def test_a_page_that_cannot_be_read_is_reported():
    client = FakeClient(error=RuntimeError('the network is down'))
    with pytest.raises(ResearchError):
        fetch('https://example.com', client=client, allow_private=True)


def test_a_huge_page_is_cut_short():
    client = FakeClient(FakeResponse('<html><body>' + 'word ' * 5000 + '</body></html>'))
    page = fetch('https://example.com', client=client, allow_private=True, max_bytes=1000)
    assert page.truncated is True


def test_the_page_becomes_prompt_context():
    page = Page(url='https://example.com/docs', title='Docs',
                text='The answer is 42.')
    context = page.as_context()
    assert 'Docs' in context
    assert 'The answer is 42.' in context
    assert 'https://example.com/docs' in context


def test_the_prompt_asks_for_the_answer_from_the_page_only():
    page = Page(url='https://example.com/docs', title='Docs', text='The answer is 42.')
    messages = build_prompt('What is the answer?', page)
    assert messages[0]['role'] == 'system'
    assert 'only from the page' in messages[0]['content']
    assert 'What is the answer?' in messages[1]['content']
    assert 'The answer is 42.' in messages[1]['content']


def test_a_question_is_required():
    with pytest.raises(ResearchError):
        research('https://example.com', '   ', router=object())


def test_the_answer_comes_from_the_provider():
    class FakeSpec:
        default_model = 'a-model'
        name = 'Fake'

    class FakeRouter:
        def spec(self, name):
            return FakeSpec()

        def stream(self, spec, model, key, messages, check, emit):
            assert model == 'a-model'
            assert 'What is the answer?' in messages[1]['content']
            return '42'

    client = FakeClient(FakeResponse(
        '<html><head><title>Docs</title></head><body><p>The answer is 42.</p></body></html>'))
    answer = research('https://example.com/docs', 'What is the answer?',
                      router=FakeRouter(), client=client, allow_private=True)
    assert answer == '42'


def test_a_page_without_text_is_reported():
    client = FakeClient(FakeResponse('<html><body></body></html>'))
    with pytest.raises(ResearchError):
        research('https://example.com', 'What?', router=object(), client=client,
                 allow_private=True)


def test_the_private_address_is_refused_before_the_page_is_read():
    client = FakeClient()
    with pytest.raises(ResearchError):
        fetch('https://pc.local/page', client=client,
              resolver=a_resolver_that_gives('192.168.1.20'))
    assert client.requested == []
