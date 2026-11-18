"""Web research: read a page and answer a question about it.

The assistant cannot wander over the internet on its own. It can do three
things, and all three need the owner:

1. the owner gives a page,
2. the page is fetched over HTTPS and turned into readable text,
3. the owner asks a question about it and the provider answers from that
   text only.

The rules that keep this safe:

- only ``https`` is allowed, and a page that resolves to a private or
  loopback address is refused, so a link cannot be used to reach the
  machines inside the owner's network;
- the page size and the time are limited, so a slow or huge page cannot
  hold the program;
- the fetched text is put in front of the provider as context. The provider
  is not asked to fetch anything itself, so it cannot follow a link that is
  in the page.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

#: The largest page that is read, in bytes.
MAX_PAGE_BYTES = 2_000_000

#: How long a page may take.
DEFAULT_TIMEOUT = 20.0

#: The user agent that is sent.
USER_AGENT = 'JARVIS-AI/0.3 (research; owner initiated)'

#: The scripts and the styles are not text.
_SCRIPT = re.compile(r'<(script|style|noscript)\b.*?</\1>', re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
_TAG = re.compile(r'<[^>]+>')
_SPACE = re.compile(r'[ \t\r\f\v]+')
_BLANK_LINES = re.compile(r'\n{3,}')


class ResearchError(RuntimeError):
    """A page could not be read."""


@dataclass
class Page:
    """A page that was read."""

    url: str
    title: str
    text: str
    status: int = 200
    truncated: bool = False

    def as_context(self, max_characters: int = 12000) -> str:
        """The page as text for a prompt."""
        head = f'# {self.title}\nSource: {self.url}\n\n' if self.title else f'Source: {self.url}\n\n'
        body = self.text[:max_characters]
        if self.truncated:
            body += '\n\n[the page was cut short]'
        return head + body


def check_address(host: str, resolver=socket.getaddrinfo) -> None:
    """Refuse a host that points into the owner's own network.

    A link in a page, or a link the owner was given, must not be able to
    reach the printer, the router or a service that listens on the local
    network only.
    """
    try:
        entries = resolver(host, None)
    except OSError as error:
        raise ResearchError(f'The address "{host}" could not be resolved: {error}') from None
    for entry in entries:
        address = entry[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (parsed.is_private or parsed.is_loopback or parsed.is_link_local
                or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified):
            raise ResearchError(
                f'The address "{host}" points inside the local network, so it was refused.')


def check_url(url: str) -> None:
    """Only HTTPS, and only a real host."""
    if not isinstance(url, str) or not url.strip():
        raise ResearchError('An address is required.')
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != 'https':
        raise ResearchError('Only an https address can be read.')
    if not parsed.hostname:
        raise ResearchError('The address has no host name.')


def readable_text(markup: str) -> tuple:
    """The readable text of a page and its title."""
    title = ''
    match = re.search(r'<title[^>]*>(.*?)</title>', markup, re.IGNORECASE | re.DOTALL)
    if match:
        title = html.unescape(re.sub(r'\s+', ' ', match.group(1))).strip()
    without_code = _COMMENT.sub(' ', markup)
    without_code = _SCRIPT.sub(' ', without_code)
    without_code = re.sub(r'<(br|/p|/div|/li|/h[1-6])[^>]*>', '\n', without_code,
                          flags=re.IGNORECASE)
    text = _TAG.sub(' ', without_code)
    text = html.unescape(text)
    text = _SPACE.sub(' ', text)
    lines = [line.strip() for line in text.splitlines()]
    text = '\n'.join(line for line in lines if line)
    text = _BLANK_LINES.sub('\n\n', text)
    return title, text


def fetch(url: str, *, client=None, timeout: float = DEFAULT_TIMEOUT,
          max_bytes: int = MAX_PAGE_BYTES, allow_private: bool = False,
          resolver=socket.getaddrinfo) -> Page:
    """Read a page over HTTPS."""
    check_url(url)
    if not allow_private:
        check_address(urlparse(url).hostname, resolver)
    if client is None:
        import httpx
        client = httpx.Client(follow_redirects=True, timeout=timeout,
                               headers={'User-Agent': USER_AGENT})
        close = True
    else:
        close = False
    try:
        response = client.get(url)
        body = response.content or b''
        truncated = len(body) > max_bytes
        markup = body[:max_bytes].decode(response.encoding or 'utf-8', 'replace')
        title, text = readable_text(markup)
        return Page(url=url, title=title, text=text, status=response.status_code,
                    truncated=truncated)
    except ResearchError:
        raise
    except Exception as error:
        raise ResearchError(f'The page could not be read: {error}') from None
    finally:
        if close:
            client.close()


def build_prompt(question: str, page: Page, max_characters: int = 12000) -> list:
    """The messages for the provider."""
    context = page.as_context(max_characters)
    system = (
        'You are JARVIS. You answer only from the page the owner gave you. '
        'If the page does not hold the answer, say so plainly. Do not invent '
        'facts, and do not mention that you were given a page.'
    )
    user = f'Page:\n{context}\n\nQuestion: {question}'
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def research(url: str, question: str, *, router=None, provider: str = '', model: str = '',
             key: str = '', client=None, check=None, emit=None, timeout: float = DEFAULT_TIMEOUT,
             allow_private: bool = False) -> str:
    """Read a page and answer a question about it.

    The provider is the same one the chat uses, so the key stays in the
    Windows vault and the routing rules stay the same.
    """
    if not (question or '').strip():
        raise ResearchError('A question is required.')
    page = fetch(url, client=client, timeout=timeout, allow_private=allow_private)
    if not page.text.strip():
        raise ResearchError('The page had no readable text.')
    messages = build_prompt(question, page)
    if router is None:
        raise ResearchError('No provider router is available.')
    spec = router.spec(provider)
    answer = router.stream(spec, model or spec.default_model, key, messages,
                            check or (lambda: None), emit or (lambda _chunk: None))
    return answer


__all__ = ['Page', 'ResearchError', 'build_prompt', 'check_address', 'check_url',
           'fetch', 'readable_text', 'research']
