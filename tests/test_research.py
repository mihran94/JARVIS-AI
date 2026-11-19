"""Web research: the page is read, and the provider answers from it."""
import ipaddress

import pytest

from research.research import (
    MAX_REDIRECTS, Page, ResearchError, build_prompt, check_address, check_url,
    fetch, readable_text, research,
)


class FakeResponse:
    def __init__(self, text='', status_code=200, content=None, encoding='utf-8',
                 headers=None, chunks=None):
        self.text = text
        self.status_code = status_code
        self.content = content if content is not None else text.encode('utf-8')
        self.encoding = encoding
        self.headers = dict(headers or {})
        self._chunks = chunks
        #: How many blocks the reader actually asked for.
        self.blocks_read = 0

    def iter_bytes(self):
        blocks = self._chunks if self._chunks is not None else [self.content]
        for block in blocks:
            self.blocks_read += 1
            yield block


class FakeStream:
    """The context manager httpx's `stream` returns."""

    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, *exception):
        return False


class FakeClient:
    """A client that answers without touching the network."""

    def __init__(self, response=None, error=None, responses=None):
        self.response = response or FakeResponse('<html><body>text</body></html>')
        self.error = error
        #: When several answers are given, they are handed out in order.
        self.responses = list(responses) if responses else None
        self.requested = []
        self.streams = []

    def stream(self, method, url, **kwargs):
        self.requested.append(url)
        self.streams.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.responses:
            return FakeStream(self.responses.pop(0))
        return FakeStream(self.response)


def a_resolver_that_gives(*addresses):
    def resolver(host, port):
        return [(2, 1, 6, '', (address, 0)) for address in addresses]
    return resolver


def a_resolver_that_maps(mapping):
    """A resolver that answers differently for different hosts."""
    def resolver(host, port):
        return [(2, 1, 6, '', (address, 0)) for address in mapping.get(host, [])]
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


def test_an_address_with_a_password_is_refused():
    """A user name and a password would be sent to the origin."""
    with pytest.raises(ResearchError):
        check_url('https://user:secret@example.com/page')


def test_an_address_with_a_space_is_refused():
    with pytest.raises(ResearchError):
        check_url('https://example.com/a page')


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


def test_the_body_is_never_held_whole():
    """The reader stops as soon as the cap is reached.

    The old code read `response.content` first, so the whole body was in
    memory before the cap was applied, and a huge answer could use all of it.
    """
    response = FakeResponse(chunks=[b'a' * 100, b'b' * 100, b'c' * 100])
    client = FakeClient(response)
    page = fetch('https://example.com', client=client, allow_private=True, max_bytes=150)
    assert page.truncated is True
    assert response.blocks_read == 2, 'the reader kept reading past the cap'
    assert len(response.content) == 0


def test_a_binary_answer_is_refused():
    client = FakeClient(FakeResponse('not really a pdf', headers={
        'content-type': 'application/pdf'}))
    with pytest.raises(ResearchError) as error:
        fetch('https://example.com/file.pdf', client=client, allow_private=True)
    assert 'not a page of text' in str(error.value)


def test_a_redirect_to_a_page_is_followed():
    client = FakeClient(responses=[
        FakeResponse('', status_code=302, headers={'location': '/moved'}),
        FakeResponse('<html><head><title>There</title></head><body><p>Here.</p></body></html>'),
    ])
    page = fetch('https://example.com/old', client=client, allow_private=True)
    assert page.title == 'There'
    assert 'Here.' in page.text
    assert client.requested == ['https://example.com/old', 'https://example.com/moved']


def test_a_redirect_to_a_private_address_is_refused():
    """A public page may answer with a redirect into the owner's network."""
    client = FakeClient(responses=[
        FakeResponse('', status_code=302,
                     headers={'location': 'https://169.254.169.254/latest/meta-data/'}),
    ])
    resolver = a_resolver_that_maps({
        'example.com': ['93.184.216.34'],
        '169.254.169.254': ['169.254.169.254'],
    })
    with pytest.raises(ResearchError):
        fetch('https://example.com/old', client=client, resolver=resolver)
    assert len(client.requested) == 1, 'the redirect was followed'
    assert not any('169.254' in url for url in client.requested), \
        'the private address was requested'


def test_a_redirect_to_http_is_refused():
    """A redirect may not undo the https rule."""
    client = FakeClient(responses=[
        FakeResponse('', status_code=302, headers={'location': 'http://example.com/plain'}),
    ])
    with pytest.raises(ResearchError):
        fetch('https://example.com/old', client=client, allow_private=True)
    assert client.requested == ['https://example.com/old']


def test_a_redirect_to_an_address_with_a_password_is_refused():
    client = FakeClient(responses=[
        FakeResponse('', status_code=302,
                     headers={'location': 'https://user:secret@example.com/x'}),
    ])
    with pytest.raises(ResearchError):
        fetch('https://example.com/old', client=client, allow_private=True)


def test_a_redirect_without_a_place_is_refused():
    client = FakeClient(responses=[FakeResponse('', status_code=302, headers={})])
    with pytest.raises(ResearchError):
        fetch('https://example.com/old', client=client, allow_private=True)


def test_too_many_redirects_are_refused():
    client = FakeClient(responses=[
        FakeResponse('', status_code=302, headers={'location': 'https://example.com/again'})
        for _ in range(MAX_REDIRECTS + 3)
    ])
    with pytest.raises(ResearchError) as error:
        fetch('https://example.com/old', client=client, allow_private=True)
    assert 'redirected too many times' in str(error.value)


def test_the_connection_is_made_to_the_checked_address():
    """The name cannot answer with a different address the second time."""
    client = FakeClient(FakeResponse('<html><body>text</body></html>'))
    fetch('https://example.com/page', client=client,
          resolver=a_resolver_that_gives('93.184.216.34'))
    assert client.requested == ['https://93.184.216.34/page']
    extensions = client.streams[0].get('extensions') or {}
    assert extensions.get('sni_hostname') == 'example.com'


def test_a_name_that_answers_with_a_private_address_is_refused():
    client = FakeClient(FakeResponse('<html><body>text</body></html>'))
    with pytest.raises(ResearchError):
        fetch('https://example.com/page', client=client,
              resolver=a_resolver_that_gives('127.0.0.1'))
    assert client.requested == []


def test_a_name_that_answers_with_a_public_and_a_private_address_is_refused():
    client = FakeClient(FakeResponse('<html><body>text</body></html>'))
    with pytest.raises(ResearchError):
        fetch('https://example.com/page', client=client,
              resolver=a_resolver_that_gives('93.184.216.34', '10.0.0.5'))
    assert client.requested == []


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
    assert 'not instructions' in messages[0]['content']
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
