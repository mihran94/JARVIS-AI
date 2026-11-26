"""Opt-in Azure neural speech synthesis. Audio remains in memory until playback."""
import asyncio
from dataclasses import dataclass
from html import escape
from io import BytesIO
import re
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from time import monotonic, sleep
import wave

import httpx

from voice.errors import VoiceUnavailable
from voice.text_tools import tokens

CREDENTIAL = 'Azure Speech'
VOICES = {
    'ta': ('ta-IN', 'ta-IN-PallaviNeural'),
    'en': ('en-US', 'en-US-JennyNeural'),
    'fr': ('fr-FR', 'fr-FR-DeniseNeural'),
}
SAMPLES = {
    'ta': 'வணக்கம். இது ஜார்விஸின் தமிழ் குரல்.',
    'en': 'Hello. This is the JARVIS English voice.',
    'fr': 'Bonjour. Voici la voix française de JARVIS.',
}
TRANSLITERATION = {
    'vanakkam': 'வணக்கம்', 'nandri': 'நன்றி', 'ippa': 'இப்போ', 'ippo': 'இப்போ',
    'enna': 'என்ன', 'ungalukku': 'உங்களுக்கு', 'ungal': 'உங்கள்',
    'naan': 'நான்', 'naanga': 'நாங்க', 'pannunga': 'பண்ணுங்க',
    'pannu': 'பண்ணு', 'pannalaam': 'பண்ணலாம்', 'sollunga': 'சொல்லுங்க',
    'seiyunga': 'செய்யுங்க', 'irukku': 'இருக்கு', 'venum': 'வேணும்',
}
FRENCH = {'bonjour', 'bonsoir', 'merci', 'vous', 'avec', 'votre', 'nous', 'pouvez',
          'francais', 'voici', 'cette', 'est', 'sont', 'pour', 'dans', 'veuillez',
          'salut', 'bienvenue', 'comment', 'allez', 'une', 'les', 'des', 'tres'}
ENGLISH = {'hello', 'the', 'this', 'your', 'you', 'please', 'with', 'can', 'will',
           'here', 'thank', 'thanks', 'and', 'from', 'what', 'good', 'are'}
MAX_AUDIO_BYTES = 8_000_000


def speech_text(text, preferred='en', *, sample_language=None):
    """Detect Tamil script and common Tanglish/French cues locally."""
    words = set(tokens(text))
    roman = words & TRANSLITERATION.keys()
    if sample_language:
        return sample_language, text
    if re.search(r'[\u0b80-\u0bff]', text) or roman:
        converted = re.sub(r'\b[A-Za-z]+\b',
                           lambda m: TRANSLITERATION.get(m[0].casefold(), m[0]), text)
        return 'ta', converted
    french, english = len(words & FRENCH), len(words & ENGLISH)
    if french != english:
        return ('fr' if french > english else 'en'), text
    return ('fr' if preferred == 'fr' else 'en'), text


def normalize_region(value):
    region = value.strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9]{1,30}', region):
        raise ValueError('Enter your Azure Speech resource region, such as francecentral.')
    return region


@dataclass(frozen=True, repr=False)
class AzureConfig:
    region: str
    key: str


def _check_response(response):
    if response.status_code in (401, 403):
        raise VoiceUnavailable('Azure Speech rejected the key or region. Check API Provider Manager.')
    if response.status_code == 429:
        raise VoiceUnavailable('Azure Speech is rate limited or the quota was reached.')
    if response.status_code != 200:
        raise VoiceUnavailable(f'Azure Speech returned HTTP {response.status_code}.')


async def synthesize(config, text, language, *, transport=None):
    region = normalize_region(config.region)
    if not config.key:
        raise VoiceUnavailable('Add an Azure Speech key in API Provider Manager.')
    locale, voice = VOICES[language]
    root = f'https://{region}.tts.speech.microsoft.com/cognitiveservices'
    headers = {'Ocp-Apim-Subscription-Key': config.key}
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{locale}"><voice name="{voice}">{escape(text)}</voice></speak>')
    try:
        async with asyncio.timeout(14), httpx.AsyncClient(
                timeout=8, follow_redirects=False, trust_env=False, transport=transport) as client:
            catalog = await client.get(f'{root}/voices/list', headers=headers)
            _check_response(catalog)
            voices = catalog.json()
            if not isinstance(voices, list) or not any(
                    isinstance(row, dict) and row.get('ShortName') == voice
                    and row.get('Locale') == locale for row in voices):
                raise VoiceUnavailable(f'{voice} is unavailable in the configured Azure region.')
            headers.update({'Content-Type': 'application/ssml+xml',
                            'X-Microsoft-OutputFormat': 'riff-24khz-16bit-mono-pcm'})
            result = bytearray()
            async with client.stream('POST', f'{root}/v1', headers=headers,
                                     content=ssml.encode('utf-8')) as response:
                _check_response(response)
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(result) + len(chunk) > MAX_AUDIO_BYTES:
                        raise VoiceUnavailable('Azure Speech returned audio beyond the playback size limit.')
                    result.extend(chunk)
            return bytes(result)
    except (httpx.RequestError, TimeoutError):
        raise VoiceUnavailable('Azure Speech could not be reached in time.') from None
    except ValueError:
        raise VoiceUnavailable('Azure Speech returned an invalid voice list.') from None


async def cancellable_synthesis(config, text, language, cancelled):
    if cancelled():
        return None
    task = asyncio.create_task(synthesize(config, text, language))
    try:
        while not task.done():
            await asyncio.wait((task,), timeout=0.1)
            if cancelled():
                return None
        return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def play_wav(data, cancelled, playing, *, expected_rate=24000):
    """Play a verified mono PCM WAV on the Windows default output device."""
    if sys.platform != 'win32':
        raise VoiceUnavailable('Speech playback requires Windows.')
    import winsound

    try:
        with wave.open(BytesIO(data), 'rb') as audio:
            rate = audio.getframerate()
            if ((audio.getnchannels(), audio.getsampwidth()) != (1, 2)
                    or not 8000 <= rate <= 48000
                    or (expected_rate is not None and rate != expected_rate)):
                raise ValueError('Unexpected WAV format')
            frames = audio.getnframes()
            if not frames or len(audio.readframes(frames)) != frames * 2:
                raise ValueError('Missing PCM data')
            duration = frames / rate
    except (EOFError, ValueError, wave.Error):
        source = 'Windows Tamil voice' if expected_rate is None else 'Azure Speech'
        raise VoiceUnavailable(f'{source} returned invalid WAV audio.') from None
    with TemporaryDirectory(prefix='jarvis-speech-') as directory:
        path = Path(directory) / 'reply.wav'
        path.write_bytes(data)
        if cancelled():
            return
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            playing()
            end = monotonic() + duration
            while not cancelled() and monotonic() < end:
                sleep(0.05)
        except RuntimeError:
            raise VoiceUnavailable('Speech playback failed. Check the Windows output device.') from None
        finally:
            winsound.PlaySound(None, 0)
