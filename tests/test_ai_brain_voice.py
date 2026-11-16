"""Tests for the AI brain and voice section.

WHAT IS COVERED
    * The provider the owner chose is remembered, and the interface says which
      provider, profile and model will answer.
    * Fast and Deep are preserved where a provider offers them, and the HUD's
      own Fast and Deep pair does not drift away from the desktop one.
    * A provider failure is classified into exactly one kind, and the kinds
      that used to be one sentence are now distinct and actionable.
    * An empty key, a network failure and a model the provider does not serve
      are three different problems with three different answers.
    * The model list is checked without sending a prompt and without putting
      the key anywhere near the answer.
    * Text chat and voice keep their existing flows, and the voice states use
      the words the owner reads.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import httpx
import pytest
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from providers import profiles
from providers.chat import (
    PROVIDERS, ProviderError, ProviderFailure, TransientProviderError, stream_chat,
)
from providers.errors import BACKUP_ELIGIBLE_KINDS, FailureKind, diagnose
from providers.models import check_model, model_list_endpoint
from providers.registry import provider_names


# ── helpers ──────────────────────────────────────────────────────────────────

def app():
    return QApplication.instance() or QApplication([])


def window(tmp_path):
    app()
    return desktop.Window(tmp_path)


def chat_request(provider=None):
    return [{'role': 'user', 'content': 'bonjour'}]


# ── provider choice ──────────────────────────────────────────────────────────

def test_every_provider_the_owner_can_choose_is_registered():
    names = set(provider_names())
    assert {'OpenAI', 'Gemini', 'Claude', 'MiniMax', 'DeepSeek', 'Groq',
            'OpenRouter', 'Ollama'} <= names


def test_the_primary_chat_provider_is_remembered(tmp_path):
    win = window(tmp_path)
    try:
        win.chat_provider.setCurrentText('OpenAI')
        assert win.store.get('chat_provider') == 'OpenAI'
        # A fresh window reads the choice back.
        again = window(tmp_path)
        try:
            assert again.chat_provider.currentText() == 'OpenAI'
        finally:
            again.close()
    finally:
        win.close()


def test_the_active_brain_names_the_provider_profile_and_model(tmp_path):
    win = window(tmp_path)
    try:
        win.chat_provider.setCurrentText('Gemini')
        text = win.brain_label.text()
        assert 'Gemini' in text and 'Fast' in text
        assert profiles.PROFILE_MODELS['Gemini']['fast'] in text
    finally:
        win.close()


def test_a_provider_without_profiles_shows_only_its_model(tmp_path):
    win = window(tmp_path)
    try:
        win.chat_provider.setCurrentText('OpenAI')
        text = win.brain_label.text()
        assert 'OpenAI' in text
        assert PROVIDERS['OpenAI'].default_model in text
    finally:
        win.close()


# ── Fast and Deep ────────────────────────────────────────────────────────────

def test_only_gemini_offers_two_profiles():
    assert profiles.supports_profiles('Gemini') is True
    for name in provider_names():
        if name != 'Gemini':
            assert profiles.supports_profiles(name) is False, name


def test_the_fast_and_deep_models_are_current_ones():
    assert profiles.PROFILE_MODELS['Gemini']['fast'] == 'gemini-3.5-flash-lite'
    assert profiles.PROFILE_MODELS['Gemini']['deep'] == 'gemini-3.8-flash'


def test_the_hud_keeps_the_same_fast_and_deep_pair():
    """The HUD and the desktop must not drift into different models."""
    import re
    from pathlib import Path
    source = Path('quantum_core/launcher.py').read_text(encoding='utf-8')
    fast = re.search(r"^MODEL\s*=\s*'([^']+)'", source, re.M)
    deep = re.search(r"^DEEP_MODEL\s*=\s*'([^']+)'", source, re.M)
    assert fast and deep, 'the HUD must name its two models'
    assert fast.group(1) == profiles.PROFILE_MODELS['Gemini']['fast']
    assert deep.group(1) == profiles.PROFILE_MODELS['Gemini']['deep']


def test_switching_the_profile_changes_the_model(tmp_path):
    win = window(tmp_path)
    try:
        win.provider.setCurrentText('Gemini')
        win.provider_profile.setCurrentIndex(
            win.provider_profile.findData('deep'))
        assert win.model.text() == profiles.PROFILE_MODELS['Gemini']['deep']
        win.provider_profile.setCurrentIndex(
            win.provider_profile.findData('fast'))
        assert win.model.text() == profiles.PROFILE_MODELS['Gemini']['fast']
    finally:
        win.close()


def test_a_model_the_owner_typed_is_not_replaced_by_a_default(tmp_path):
    win = window(tmp_path)
    try:
        win.provider.setCurrentText('Gemini')
        win.provider_profile.setCurrentIndex(
            win.provider_profile.findData('fast'))
        win.model.setText('gemini-3.8-flash')
        win.save_provider()
        assert win.selected_model('Gemini') == 'gemini-3.8-flash'
    finally:
        win.close()


def test_a_provider_without_profiles_keeps_its_single_model(tmp_path):
    win = window(tmp_path)
    try:
        win.provider.setCurrentText('OpenAI')
        assert win.provider_profile.count() == 1
        assert win.model.text() == PROVIDERS['OpenAI'].default_model
    finally:
        win.close()


# ── failure classification ───────────────────────────────────────────────────

def test_a_404_that_names_a_model_is_a_model_problem():
    body = {'error': {'message': 'models/gemini-9.9 is not found for API version v1beta'}}
    result = diagnose('Gemini', status=404, body=body, model='gemini-9.9')
    assert result.kind == FailureKind.MODEL_UNAVAILABLE
    assert 'gemini-9.9' in result.message


def test_a_404_that_names_the_url_is_an_endpoint_problem():
    body = {'error': {'message': 'The requested URL was not found on this server.'}}
    result = diagnose('Gemini', status=404, body=body, model='gemini-3.8-flash')
    assert result.kind == FailureKind.WRONG_ENDPOINT
    assert 'endpoint' in result.title.lower()


def test_a_404_with_no_evidence_keeps_the_cause_unknown():
    result = diagnose('Gemini', status=404, body={'error': {'message': 'nothing useful'}})
    assert result.kind == FailureKind.UNKNOWN
    assert 'model availability' in result.hint


def test_a_400_that_says_the_key_is_wrong_is_a_credential_problem():
    body = {'error': {'message': 'API key not valid. Please pass a valid API key.'}}
    result = diagnose('Gemini', status=400, body=body)
    assert result.kind == FailureKind.INVALID_CREDENTIALS


def test_a_401_and_a_403_are_different_problems():
    assert diagnose('OpenAI', status=401).kind == FailureKind.INVALID_CREDENTIALS
    assert diagnose('OpenAI', status=403).kind == FailureKind.NO_ACCESS


def test_a_429_is_split_into_quota_and_rate_limit():
    quota = diagnose('OpenAI', status=429, body={'error': {'message': 'quota exceeded'}})
    rate = diagnose('OpenAI', status=429, body={'error': {'message': 'rate limit reached'}})
    assert quota.kind == FailureKind.QUOTA
    assert rate.kind == FailureKind.RATE_LIMIT
    assert rate.retryable is True


def test_a_500_is_not_a_transient_failure():
    """A 500 is this request failing on the provider's side, not an outage."""
    result = diagnose('OpenAI', status=500)
    assert result.kind == FailureKind.SERVER_ERROR
    assert result.retryable is False
    assert result.kind not in BACKUP_ELIGIBLE_KINDS


def test_a_gateway_outage_is_transient():
    for status in (502, 503, 504):
        result = diagnose('OpenAI', status=status)
        assert result.kind == FailureKind.TRANSIENT
        assert result.retryable is True
        assert result.kind in BACKUP_ELIGIBLE_KINDS


def test_a_network_failure_and_a_bad_key_are_different_problems():
    network = diagnose('OpenAI', error=httpx.ConnectError('connection refused'))
    timeout = diagnose('OpenAI', error=httpx.ReadTimeout('timed out'))
    assert network.kind == FailureKind.NETWORK
    assert timeout.kind == FailureKind.TIMEOUT
    assert diagnose('OpenAI', status=401).kind != network.kind


def test_no_key_at_all_is_its_own_problem():
    result = diagnose('OpenAI', key='')
    assert result.kind == FailureKind.EMPTY_KEY
    assert 'API Providers' in result.hint


def test_the_diagnosis_never_repeats_the_body_or_the_key():
    result = diagnose('Gemini', status=401, body='private-secret', key='private-secret')
    assert 'private-secret' not in result.message
    assert 'private-secret' not in result.hint
    assert 'private-secret' not in result.title


# ── the chat path uses the classifier ────────────────────────────────────────

def test_the_gemini_404_is_classified_and_names_the_recommended_model():
    def respond(request):
        return httpx.Response(404, json={'error': {'message':
            'models/gemini-2.5-flash is not found for API version v1beta: provider-private-value'}})

    with pytest.raises(ProviderFailure) as failure:
        stream_chat('Gemini', 'gemini-2.5-flash', 'test-secret', chat_request('Gemini'),
                    lambda: None, lambda _: None, transport=httpx.MockTransport(respond))
    assert failure.value.kind == FailureKind.MODEL_UNAVAILABLE
    assert PROVIDERS['Gemini'].default_model in str(failure.value)
    assert 'provider-private-value' not in str(failure.value)
    assert 'test-secret' not in str(failure.value)


def test_only_a_transient_failure_may_use_the_backup():
    """A bad key or an exhausted quota must never spend the backup provider."""
    for status, kind in ((401, FailureKind.INVALID_CREDENTIALS),
                         (429, FailureKind.RATE_LIMIT),
                         (500, FailureKind.SERVER_ERROR)):
        with pytest.raises(ProviderError) as error:
            stream_chat('OpenAI', 'm', 'fake', chat_request('OpenAI'), lambda: None, lambda _: None,
                        transport=httpx.MockTransport(lambda _: httpx.Response(status)))
        assert not isinstance(error.value, TransientProviderError), status
        assert error.value.kind == kind


def test_a_transient_failure_is_the_only_one_marked_for_the_backup():
    with pytest.raises(TransientProviderError) as error:
        stream_chat('OpenAI', 'm', 'fake', chat_request('OpenAI'), lambda: None, lambda _: None,
                    transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    assert error.value.kind == FailureKind.TRANSIENT


def test_a_network_failure_is_transient_and_never_carries_the_key():
    def fail(request):
        raise httpx.ConnectError('connection refused')

    with pytest.raises(TransientProviderError) as error:
        stream_chat('OpenAI', 'm', 'the-secret-key', chat_request('OpenAI'),
                    lambda: None, lambda _: None, transport=httpx.MockTransport(fail))
    assert error.value.kind == FailureKind.NETWORK
    assert 'the-secret-key' not in str(error.value)


def test_an_empty_key_is_refused_before_any_request():
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, text='data: [DONE]\n\n')

    with pytest.raises(ProviderError, match='Configure an API key'):
        stream_chat('OpenAI', 'm', '', chat_request('OpenAI'), lambda: None, lambda _: None,
                    transport=httpx.MockTransport(respond))
    assert sent == []


# ── model availability ───────────────────────────────────────────────────────

def test_the_model_list_endpoint_is_derived_per_provider():
    assert model_list_endpoint('Gemini', PROVIDERS['Gemini'].endpoint) == \
        'https://generativelanguage.googleapis.com/v1beta/models'
    assert model_list_endpoint('OpenAI', PROVIDERS['OpenAI'].endpoint) == \
        'https://api.openai.com/v1/models'
    assert model_list_endpoint('Claude', 'https://api.anthropic.com/v1/messages') == \
        'https://api.anthropic.com/v1/models'


def test_a_model_the_provider_serves_is_confirmed():
    def respond(request):
        return httpx.Response(200, json={
            'models': [{'name': 'models/gemini-3.8-flash',
                        'supportedGenerationMethods': ['generateContent']}]})

    result = check_model('Gemini', PROVIDERS['Gemini'].endpoint, 'gemini-3.8-flash', 'fake',
                         transport=httpx.MockTransport(respond))
    assert result.available is True and result.known is True
    assert 'gemini-3.8-flash' in result.detail


def test_a_model_the_provider_does_not_serve_is_refused():
    def respond(request):
        return httpx.Response(200, json={
            'models': [{'name': 'models/gemini-3.8-flash',
                        'supportedGenerationMethods': ['generateContent']}]})

    result = check_model('Gemini', PROVIDERS['Gemini'].endpoint, 'gemini-9.9-ultra', 'fake',
                         transport=httpx.MockTransport(respond))
    assert result.available is False and result.known is True
    assert 'gemini-9.9-ultra' in result.detail


def test_a_failed_model_list_explains_itself_and_keeps_the_key_out():
    def respond(request):
        return httpx.Response(401, text='private-secret')

    result = check_model('Gemini', PROVIDERS['Gemini'].endpoint, 'gemini-3.8-flash', 'fake-key',
                         transport=httpx.MockTransport(respond))
    assert result.known is False
    assert result.diagnosis is not None
    assert result.diagnosis.kind == FailureKind.INVALID_CREDENTIALS
    assert 'private-secret' not in result.detail
    assert 'fake-key' not in result.detail


def test_the_model_check_sends_no_prompt():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={'data': [{'id': 'gpt-4.1-mini'}]})

    check_model('OpenAI', PROVIDERS['OpenAI'].endpoint, 'gpt-4.1-mini', 'fake',
                transport=httpx.MockTransport(respond))
    assert len(seen) == 1
    assert seen[0].method == 'GET'


@pytest.mark.parametrize('catalogue_id', ['gpt-4.1-2025-04-14', 'gpt-4.1-mini'])
def test_related_catalogue_ids_do_not_confirm_the_configured_model(catalogue_id):
    def respond(request):
        return httpx.Response(200, json={'data': [{'id': catalogue_id}]})

    result = check_model('OpenAI', PROVIDERS['OpenAI'].endpoint, 'gpt-4.1', 'fake',
                         transport=httpx.MockTransport(respond))
    assert result.available is False and result.known is True


def test_gemini_model_catalogue_follows_next_page():
    def respond(request):
        token = request.url.params.get('pageToken')
        if token is None:
            return httpx.Response(200, json={
                'models': [{'name': 'models/gemini-other'}], 'nextPageToken': 'page-two'})
        assert token == 'page-two'
        return httpx.Response(200, json={'models': [{'name': 'models/gemini-target'}]})

    result = check_model('Gemini', PROVIDERS['Gemini'].endpoint, 'gemini-target', 'fake',
                         transport=httpx.MockTransport(respond))
    assert result.available is True and result.known is True


# ── the interface ────────────────────────────────────────────────────────────

def test_saving_a_provider_in_the_manager_switches_the_chat_provider(tmp_path):
    win = window(tmp_path)
    try:
        win.provider.setCurrentText('OpenAI')
        win.save_provider()
        assert win.chat_provider.currentText() == 'OpenAI'
    finally:
        win.close()


def test_the_backup_provider_is_remembered_and_only_used_when_enabled(tmp_path):
    win = window(tmp_path)
    try:
        win.backup_provider.setCurrentText('Groq')
        assert win.store.get('backup_provider') == 'Groq'
        assert win.backup_consent.isChecked() is False
    finally:
        win.close()


def test_the_hud_status_never_carries_a_key():
    """The browser must never receive a credential."""
    import re
    from pathlib import Path
    source = Path('quantum_core/launcher.py').read_text(encoding='utf-8')
    body = re.search(r"def hud_info\(self\):\n(.*?)\n\n", source, re.S)
    assert body, 'the HUD must report its model status'
    assert 'key' not in body.group(1).casefold()


def test_the_hud_names_the_provider_and_the_four_voice_states():
    from pathlib import Path
    source = Path('quantum_core/web/index.html').read_text(encoding='utf-8')
    for word in ('Listening', 'Thinking', 'Speaking', 'Voice idle'):
        assert word in source, word
    assert 'info.provider' in source


# ── voice ────────────────────────────────────────────────────────────────────

def test_the_speech_language_can_be_chosen(tmp_path):
    win = window(tmp_path)
    try:
        assert win.voice_panel.language_code == 'en'
        win.voice_panel.set_language('ta')
        assert win.voice_panel.language_code == 'ta'
        assert win.store.get('voice_language') == 'ta'
        assert win.voice_panel.set_language('not-a-language') is False
    finally:
        win.close()


def test_the_voice_states_use_the_words_the_owner_reads(tmp_path):
    win = window(tmp_path)
    try:
        win.set_ai_visual_state('idle')
        assert win.hud_voice_status.text() == 'IDLE'
        win.set_ai_visual_state('thinking')
        assert win.hud_voice_status.text() == 'THINKING'
        win.set_ai_visual_state('listening')
        assert win.hud_voice_status.text() == 'LISTENING'
        win.set_ai_visual_state('speaking')
        assert win.hud_voice_status.text() == 'SPEAKING'
    finally:
        win.close()


def test_a_missing_language_voice_is_reported_clearly():
    from desktop.voice_panel import VoiceSpeakerWorker

    class Speaker:
        def select_language(self, language):
            return False

        def speak(self, text, language=None, rate=None):
            raise AssertionError('it must not try to speak without a voice')

    worker = VoiceSpeakerWorker(Speaker, 'bonjour', 'fr')
    messages = []
    worker.failed.connect(messages.append)
    worker.run()
    assert messages and 'Français' in messages[0]
    assert 'language pack' in messages[0]


def test_tamil_text_is_spoken_with_a_tamil_voice():
    from desktop.voice_panel import VoiceSpeakerWorker

    chosen = []

    class Speaker:
        def select_language(self, language):
            chosen.append(language)
            return True

        def speak(self, text, language=None, rate=None):
            chosen.append(('spoke', language))

    worker = VoiceSpeakerWorker(Speaker, 'வணக்கம்', 'en')
    worker.run()
    assert 'ta' in chosen
