"""One place that turns a provider failure into a sentence the owner can act on.

WHAT WAS WRONG WITH THIS
    The chat path raised `ProviderError(f'{provider} HTTP {code}. Check key, model, '
    'quota and access.')` for every failure that was not a 502/503/504. One
    sentence covered five different problems.

    The worst case was Gemini. Google answers HTTP 404 for a model that does
    not exist for the API version, and HTTP 404 for an endpoint that does not
    exist. It answers HTTP 400 for an API key that is not valid, and HTTP 429
    for a quota that is exhausted. All four arrived as the same sentence, so
    the only way to find out what was actually wrong was to guess and retry.

    A wrong endpoint and an unavailable model have opposite fixes. One needs
    a corrected URL, the other needs a different model ID. Telling the owner
    to "check key, model, quota and access" is not an actionable error; it is
    a list of things to think about.

WHAT THIS DOES NOW
    Every provider failure is classified into exactly one kind, and each kind
    carries its own title, its own sentence and its own next step:

        model_unavailable     the model ID is not served for this key or API version
        wrong_endpoint        the URL is wrong; the provider never saw a model
        invalid_credentials   the key is missing, malformed or not accepted
        no_access             the key is valid but is not allowed to use this
        quota                 the quota or billing is exhausted
        rate_limit            the request rate is too high; retry shortly
        bad_request           the request itself was rejected
        empty_key             no key is configured at all
        network               the provider could not be reached
        timeout               the provider did not answer in time
        transient             the provider is temporarily failing
        unknown               something else; the status is reported as-is

    The classifier reads the response body, because the status code alone
    cannot tell a bad model from a bad URL and a bad key from an empty quota.
    The body is only ever used to decide the KIND of failure. It is never
    echoed back in full, because a provider body can contain the key that was
    sent, and this text ends up in a message box and in a screenshot.

WHAT THIS MODULE WILL NOT DO
    * It never contacts a provider. It classifies what it is given, so it is
      testable without a network and without a key.
    * It never guesses a provider's health from one failure.
    * It never returns the raw body, so a key cannot leak through an error
      message.
"""
from __future__ import annotations

from dataclasses import dataclass


class FailureKind:
    """The kinds of failure a provider request can end in."""

    MODEL_UNAVAILABLE = 'model_unavailable'
    WRONG_ENDPOINT = 'wrong_endpoint'
    INVALID_CREDENTIALS = 'invalid_credentials'
    NO_ACCESS = 'no_access'
    QUOTA = 'quota'
    RATE_LIMIT = 'rate_limit'
    BAD_REQUEST = 'bad_request'
    EMPTY_KEY = 'empty_key'
    SERVER_ERROR = 'server_error'
    NETWORK = 'network'
    TIMEOUT = 'timeout'
    TRANSIENT = 'transient'
    UNKNOWN = 'unknown'


#: Kinds where the same request can work if it is simply sent again.
#:
#: A rate limit is deliberately NOT in this set. Throttling is not a service
#: failure, and the one backup attempt the owner can consent to is for a
#: service that is not answering, not for a key that is being throttled.
RETRYABLE_KINDS = frozenset({FailureKind.RATE_LIMIT, FailureKind.NETWORK,
                              FailureKind.TIMEOUT, FailureKind.TRANSIENT})

#: The kinds that justify the one backup attempt the owner can consent to.
#:
#: This is deliberately narrower than `RETRYABLE_KINDS`: it is the set where
#: the provider itself is not answering, so a second provider is a sensible
#: answer to the request rather than a way around a limit.
BACKUP_ELIGIBLE_KINDS = frozenset({FailureKind.NETWORK, FailureKind.TIMEOUT,
                                   FailureKind.TRANSIENT})


@dataclass(frozen=True)
class Diagnosis:
    """What went wrong, and what to do about it."""

    kind: str
    title: str
    message: str
    hint: str
    provider: str
    retryable: bool = False
    status: int | None = None
    model: str | None = None

    @property
    def actionable(self) -> bool:
        """True when the owner can do something specific about this."""
        return self.kind != FailureKind.UNKNOWN

    def as_dict(self) -> dict:
        """A plain dictionary for the HUD and for the usage log."""
        return {
            'kind': self.kind,
            'title': self.title,
            'message': self.message,
            'hint': self.hint,
            'provider': self.provider,
            'retryable': self.retryable,
            'status': self.status,
            'model': self.model,
        }


def _body_text(body) -> str:
    """The body as lower-case text, or '' when there is none."""
    if body is None:
        return ''
    if isinstance(body, bytes):
        body = body.decode('utf-8', 'replace')
    if not isinstance(body, str):
        body = str(body)
    return body[:4000].casefold()


def _mentions(body: str, *needles: str) -> bool:
    """True when the body mentions any of the phrases."""
    return any(needle in body for needle in needles)


def _model_in_body(body: str) -> bool:
    """True when the body names a model, which is how a 404 says "wrong model"."""
    if _mentions(body, 'models/', 'is not found for api version',
                 'is not supported for generatecontent', 'model_not_found',
                 'model not found', 'unknown model', 'does not exist'):
        return True
    return 'model' in body and ('not found' in body or 'not supported' in body
                                or 'does not exist' in body)


def _endpoint_in_body(body: str) -> bool:
    """True when the body says the URL was not found, rather than a model."""
    return _mentions(body, 'requested url', 'unrecognized request url', 'invalid url',
                     'unknown path', 'unknown endpoint', 'no such endpoint',
                     'not found on this server', 'the requested url was not found')


def _key_in_body(body: str) -> bool:
    """True when the body says the key is the problem."""
    return _mentions(body, 'api key not valid', 'api key is invalid', 'invalid api key',
                     'invalid_api_key', 'incorrect api key', 'unauthorized', 'invalid bearer token',
                     'no auth credentials', 'missing api key', 'api key required',
                     'authentication_error', 'invalid authentication')


def _quota_in_body(body: str) -> bool:
    """True when the body says the quota or the billing is the problem."""
    return _mentions(body, 'quota', 'billing', 'payment', 'credit balance',
                     'insufficient funds', 'exhausted', 'spending limit',
                     'free tier', 'resource_exhausted', 'out of credit')


def _rate_in_body(body: str) -> bool:
    """True when the body says the request rate is the problem."""
    return _mentions(body, 'rate limit', 'rate_limit', 'too many requests',
                     'requests per', 'slow down')


def diagnose(provider: str, *, status: int | None = None, body=None, model: str | None = None,
             key: str | None = None, error: BaseException | None = None,
             recommended: str | None = None) -> Diagnosis:
    """Classify one provider failure.

    `status` is the HTTP status, `body` the response text, `model` the model
    that was requested, `recommended` the model the provider suggests and
    `error` the transport exception, if any. `key` is only ever tested for
    emptiness; it is never included in the result.
    """
    provider = str(provider or 'Provider')
    text = _body_text(body)
    name = provider
    fallback = recommended or ''

    def model_hint() -> str:
        if fallback:
            return ('Open API Providers, use the recommended model '
                    f'{fallback}, or enter a model ID your account can actually use, '
                    'then test the connection again.')
        return ('Open API Providers, use the recommended model, or enter a model ID '
                'your account can actually use, then test the connection again.')

    def make(kind, title, message, hint, retryable=False):
        return Diagnosis(kind=kind, title=title, message=message, hint=hint,
                         provider=name, retryable=retryable, status=status, model=model)

    # A missing key is refused before a request is ever made, so it is the
    # first thing to rule out.
    if key is not None and not str(key).strip() and status is None and error is None:
        return make(FailureKind.EMPTY_KEY, 'No API key',
                    f'{provider} has no stored key.',
                    'Open API Providers, enter the key, and save it to Windows Credential Manager.')

    # Transport failures carry no status code.
    if error is not None:
        return _diagnose_transport(provider, error, model)

    if status is None:
        return make(FailureKind.UNKNOWN, 'Provider failure',
                    f'{provider} did not answer.',
                    'Try again. If it keeps happening, check the provider status page.')

    if status in (502, 503, 504):
        return make(FailureKind.TRANSIENT, f'{provider} is temporarily unavailable',
                    f'{provider} answered HTTP {status}.',
                    'Wait a minute and try again. Nothing is wrong with the configuration.',
                    retryable=True)

    if status == 401:
        return make(FailureKind.INVALID_CREDENTIALS, 'Key rejected',
                    f'{provider} rejected the key (HTTP 401).',
                    'The key is missing, revoked or typed incorrectly. Save it again in API Providers.')

    if status == 403:
        return make(FailureKind.NO_ACCESS, 'Key cannot use this',
                    f'{provider} accepted the key but refused this request (HTTP 403).',
                    'The key has no permission for this model or project. Check the provider '
                    'console for project permissions and enabled APIs.')

    if status == 404:
        if _model_in_body(text):
            return make(FailureKind.MODEL_UNAVAILABLE, 'Model not available',
                        f'{provider} does not serve the model'
                        + (f' {model}.' if model else '.'),
                        model_hint())
        if _endpoint_in_body(text):
            return make(FailureKind.WRONG_ENDPOINT, 'Wrong endpoint',
                        f'{provider} answered HTTP 404 for this URL.',
                        'The endpoint is wrong, so the provider never saw a model. Open API '
                        'Providers and check the HTTPS endpoint against your provider account.')
        return make(FailureKind.UNKNOWN, 'HTTP 404 — cause unknown',
                    f'{provider} did not identify what was missing.',
                    'Check model availability and test the saved connection in API Providers.')

    if status == 429:
        if _quota_in_body(text):
            return make(FailureKind.QUOTA, 'Quota exhausted',
                        f'{provider} refused the request because the quota is exhausted (HTTP 429).',
                        'Add credit or raise the quota in the provider console, then try again.')
        return make(FailureKind.RATE_LIMIT, 'Too many requests',
                    f'{provider} is rate limiting this key (HTTP 429).',
                    'Wait a few seconds and try again. Reduce how often JARVIS sends requests.',
                    retryable=True)

    if status == 400:
        if _key_in_body(text):
            return make(FailureKind.INVALID_CREDENTIALS, 'Key rejected',
                        f'{provider} rejected the key (HTTP 400).',
                        'The key is not valid for this provider. Save it again in API Providers '
                        'and check that it belongs to this service.')
        if _model_in_body(text):
            return make(FailureKind.MODEL_UNAVAILABLE, 'Model not available',
                        f'{provider} does not serve the model'
                        + (f' {model}.' if model else '.'),
                        model_hint())
        return make(FailureKind.BAD_REQUEST, 'Request rejected',
                    f'{provider} rejected the request (HTTP 400).',
                    'The request itself was refused. Try a shorter message and check the model ID.')

    if status == 422:
        return make(FailureKind.BAD_REQUEST, 'Request rejected',
                    f'{provider} rejected the request (HTTP 422).',
                    'The request was understood but could not be processed. Check the model ID.')

    if status in (500, 501, 505, 507, 508, 510, 511):
        # A 500 is the provider failing on THIS request, not the service being
        # down, so it does not justify the one backup attempt. 502, 503 and
        # 504 are gateway-level and are handled above as transient.
        return make(FailureKind.SERVER_ERROR, f'{provider} reported a server error',
                    f'{provider} answered HTTP {status}.',
                    'The provider rejected the request on its own side. Check the provider status '
                    'page, then try again with a shorter message.')

    if 500 <= status <= 599:
        return make(FailureKind.TRANSIENT, f'{provider} is temporarily unavailable',
                    f'{provider} answered HTTP {status}.',
                    'Wait a minute and try again.', retryable=True)

    if status == 200:
        return make(FailureKind.UNKNOWN, 'Provider failure',
                    f'{provider} answered HTTP 200 but the response was not usable.',
                    'The provider replied but the answer could not be read. Try again.')

    return make(FailureKind.UNKNOWN, f'{provider} answered HTTP {status}',
                f'{provider} answered HTTP {status}.',
                'Check the provider status page and your account settings.')


def _diagnose_transport(provider: str, error: BaseException, model: str | None) -> Diagnosis:
    """Classify a failure that never reached an HTTP status."""
    try:
        import httpx
    except ImportError:
        httpx = None

    name = provider
    text = str(error).casefold()

    if httpx is not None:
        if isinstance(error, httpx.TimeoutException):
            return Diagnosis(FailureKind.TIMEOUT, 'Provider timed out',
                             f'{provider} did not answer in time.',
                             'The connection worked but the answer was too slow. Check your network '
                             'and try again.', provider=name, retryable=True, model=model)
        if isinstance(error, httpx.ConnectError):
            return Diagnosis(FailureKind.NETWORK, 'Cannot reach the provider',
                             f'{provider} could not be reached.',
                             'Check the internet connection, a firewall, or a proxy. The key was not '
                             'sent.', provider=name, retryable=True, model=model)
        if isinstance(error, httpx.HTTPError):
            return Diagnosis(FailureKind.NETWORK, 'Secure connection failed',
                             f'The secure connection to {provider} failed.',
                             'A proxy or TLS inspection tool may be blocking the request. '
                             'The key was not sent.', provider=name, retryable=True, model=model)

    if 'certificate' in text or 'ssl' in text or 'tls' in text:
        return Diagnosis(FailureKind.NETWORK, 'Secure connection failed',
                         f'The secure connection to {provider} failed.',
                         'A proxy or TLS inspection tool may be blocking the request.',
                         provider=name, retryable=True, model=model)
    if 'name or service not known' in text or 'nodename nor servname' in text or 'dns' in text:
        return Diagnosis(FailureKind.NETWORK, 'Cannot find the provider',
                         f'The address of {provider} could not be resolved.',
                         'Check the internet connection and the DNS settings.',
                         provider=name, retryable=True, model=model)
    if 'connection refused' in text:
        return Diagnosis(FailureKind.NETWORK, 'Cannot reach the provider',
                         f'{provider} refused the connection.',
                         'Check the internet connection and any firewall. The key was not sent.',
                         provider=name, retryable=True, model=model)

    return Diagnosis(FailureKind.UNKNOWN, 'Provider failure',
                     f'{provider} could not be reached.',
                     'Try again. If it keeps happening, check the provider status page.',
                     provider=name, model=model)


def diagnosis_message(diagnosis: Diagnosis) -> str:
    """One line for a status bar: the title, the sentence and the next step."""
    return f'{diagnosis.title}. {diagnosis.message} {diagnosis.hint}'
