"""Local launcher for the Quantum Core Eel HUD.

The microphone is opened only after the owner allowed it, and the recorded
audio never leaves this PC. The HUD recognises speech with the project's own
Windows System.Speech adapter, and there is no cloud service to fall back to.
"""
import argparse
from datetime import datetime
import importlib
import os
from pathlib import Path
import re
import sys
import threading

from bottle import Bottle, abort, request
import eel
from gevent.lock import Semaphore
from gevent.threadpool import ThreadPool
import psutil

if __package__:
    from .device_tools import DEVICE_ACTIONS, DeviceError, run_device_action
    from .local_diagnostics import DiagnosticError, REPORTS, read_network_report
    from .studio_project import STUDIO_NAME, STUDIO_URL, studio_update_prompt
else:
    from device_tools import DEVICE_ACTIONS, DeviceError, run_device_action
    from local_diagnostics import DiagnosticError, REPORTS, read_network_report
    from studio_project import STUDIO_NAME, STUDIO_URL, studio_update_prompt


MODEL = 'gemini-3.5-flash-lite'
DEEP_MODEL = 'gemini-3.8-flash'
APP_VERSION = '0.3.0'
MAX_COMMAND_LENGTH = 4000
SYSTEM_INSTRUCTION = (
    'You are J.A.R.V.I.S., a capable AI assistant. Reply in the user’s language '
    'in one to three short, natural sentences suitable for spoken playback. '
    'Address the user respectfully as Sir or Boss when it fits. '
    'You have no access to PC controls. Never claim to have executed actions.'
)
TIME_COMMANDS = {
    '/time', 'time', 'current time', 'what time is it', 'what is the time',
    "what's the time", 'நேரம்', 'இப்போ நேரம் என்ன', 'quelle heure est-il',
}
STATUS_COMMANDS = {
    '/status', 'status', 'system status', 'system stats', 'cpu', 'ram', 'cpu load',
    'ram usage', 'கணினி நிலை', 'état du système',
}

#: How long one listening turn may take. The local recogniser is bounded.
LISTEN_TIMEOUT_SECONDS = 5.0

#: What the owner is told about the microphone, in plain words.
LOCAL_RECOGNITION_NOTE = (
    'Speech recognition runs locally on this PC. No microphone audio is sent to '
    'any network service.'
)


DRAFT_INSTRUCTIONS = {
    '/flow': (
        'Draft a prompt for Google Flow from the brief. Include the subject, setting, shot framing, '
        'camera movement, lighting, timing and sound when specified. Return only the paste-ready prompt.'
    ),
    '/higgsfield': (
        'Draft a prompt for Higgsfield from the brief. Describe the shot, subject movement, camera movement '
        'and visual style. Return only the paste-ready prompt.'
    ),
    '/fiverr': (
        'Draft a concise, professional Fiverr client reply in the requested language. '
        'Use only supplied facts. Do not invent commitments, rates, or delivery dates. Return the draft only.'
    ),
    '/website': (
        'Draft website copy for the brief, in the language requested. '
        'Use only supplied facts and clearly mark any missing details. Return the draft only.'
    ),
    '/upgrade': (
        'Write a reviewable proposal for this JARVIS feature brief. Include intended behavior, '
        'likely areas to inspect, tests and rollback. Flag assumptions about the source. '
        'Return a plan for a human maintainer.'
    ),
    '/app': (
        'Draft a complete standalone HTML5 document for this app idea. Return only HTML with inline CSS '
        'and JavaScript and no Markdown fences. Include accessible labels and responsive layout. '
        'Do not require API keys, remote scripts, package installs or external services.'
    ),
}



class GeminiChat:
    """Lazily initialize a single session owned by the native worker."""

    def __init__(self, key, model, coding_model=DEEP_MODEL):
        self.key = key
        self.models = {'fast': model, 'deep': coding_model}
        self.profile = 'fast'
        self.client = None
        self.sessions = {}

    @property
    def model(self):
        return self.models[self.profile]

    def get_client(self):
        from google import genai
        from google.genai import types

        if self.client is None:
            self.client = genai.Client(
                api_key=self.key,
                http_options=types.HttpOptions(
                    timeout=25_000, retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self.client

    def draft(self, command, brief):
        from google.genai import types

        result = self.get_client().models.generate_content(
            model=self.model,
            contents=brief,
            config=types.GenerateContentConfig(system_instruction=DRAFT_INSTRUCTIONS[command]),
        )
        return (result.text or '').strip()

    def reply(self, command):
        from google.genai import errors, types

        if self.profile not in self.sessions:
            self.sessions[self.profile] = self.get_client().chats.create(
                model=self.model,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.7,
                ),
            )
        try:
            result = self.sessions[self.profile].send_message(command)
        except errors.APIError as error:
            return {
                400: 'Gemini rejected the request. Check your API key and model settings, Sir.',
                401: 'Gemini could not authenticate the API key, Sir.',
                403: 'This key does not have access to Gemini, Sir.',
                404: 'That Gemini model is unavailable for this key. Check your Fast or Deep model settings, Sir.',
                429: 'Gemini reached a rate or quota limit, Sir. Check Google AI Studio.',
            }.get(error.code, 'Gemini is temporarily unavailable, Sir.')
        text = (result.text or '').strip()
        return re.sub(r'[*`]', '', text).strip() or 'Gemini returned no text, Sir.'


def voice_layer(name):
    """Import one module of the project's voice layer.

    The HUD is started from the repository root (`main.py --hud`) and also from
    inside `quantum_core` (`python launcher.py`), so the repository root is put
    on the path when the voice layer cannot be found there yet.
    """
    try:
        return importlib.import_module('voice.' + name)
    except ImportError:
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        return importlib.import_module('voice.' + name)


def voice_error():
    """The exception the voice layer raises when it refuses an operation."""
    try:
        return voice_layer('errors').VoiceError
    except ImportError:
        return RuntimeError


def speech_language(locale):
    """Map a locale such as `ta-IN` to the language the local recogniser knows.

    The Windows recogniser needs an installed speech pack per language. A
    language it does not know falls back to English, never to a cloud service.
    """
    languages = voice_layer('windows_stt').SPEECH_LANGUAGES
    code = str(locale or '').strip().casefold().replace('_', '-').split('-')[0]
    return code if code in languages else 'en'


def local_recognizer(consent, language):
    """Build the project's own offline speech recogniser.

    Recognition runs on this PC through Windows System.Speech. When this
    machine cannot run that recogniser, the microphone stays closed: there is
    no cloud service to fall back to.
    """
    windows_stt = voice_layer('windows_stt')
    return windows_stt.WindowsSpeechRecognizer(
        consent=consent, language=speech_language(language))


def ask_for_microphone(consent, answer=None):
    """Ask the owner, in the terminal, whether the microphone may be opened.

    The permission is kept in `VoiceConsent`, the single place where the
    microphone permission of this project lives. Only an explicit yes opens
    the microphone; an empty answer, a "no" and a missing terminal all leave
    it closed.
    """
    print('The microphone is closed by default.')
    print(LOCAL_RECOGNITION_NOTE)
    reader = answer if answer is not None else input
    try:
        reply = reader('Allow the microphone for this session? [y/N]: ')
    except (EOFError, KeyboardInterrupt, OSError):
        print('No answer was given, so the microphone stays closed.')
        return False
    if str(reply).strip().casefold() in ('y', 'yes'):
        consent.grant()
        print('The microphone is allowed for this session.')
        return True
    print('The microphone stays closed. JARVIS will not listen.')
    return False


def watch_for_stop(consent, on_stop=None, on_resume=None):
    """Let the owner close the microphone from the terminal.

    The watcher reads one word from the keyboard in a thread of its own.
    Typing `stop` closes the microphone and invalidates the permission, the
    way the emergency stop of the voice panel does; typing `resume` asks for
    the microphone again. The watcher never opens the microphone itself and
    never sends anything anywhere.
    """
    def watch():
        while True:
            try:
                line = input('')
            except (EOFError, KeyboardInterrupt, OSError):
                return
            command = line.strip().casefold()
            if command in ('stop', 'quit'):
                consent.stop()
                if on_stop is not None:
                    on_stop()
                return
            if command in ('resume', 'start'):
                try:
                    consent.resume()
                    consent.grant()
                except voice_error():
                    continue
                if on_resume is not None:
                    on_resume()

    thread = threading.Thread(target=watch, name='jarvis-microphone-stop', daemon=True)
    thread.start()
    return thread


class QuantumCore:
    """Eel calls run on the event loop. Blocking work runs on one native thread."""

    def __init__(self, chat, *, speak, listen, language, consent=None, recognizer=None):
        self.chat = chat
        self.voice_enabled = speak
        self.mic_enabled = listen
        self.language = language
        self.consent = consent if consent is not None else voice_layer('consent').VoiceConsent()
        self.recognizer = recognizer
        self.voice_loop_started = False
        self.engine = None
        self.worker = ThreadPool(1)
        self.turn = Semaphore(1)

    def state(self, state, message=''):
        eel.update_hud_state(state, message)

    def system_metrics(self):
        if self.mic_enabled and not self.voice_loop_started:
            self.voice_loop_started = True
            self.state('ONLINE', 'Mic enabled. ' + LOCAL_RECOGNITION_NOTE)
            eel.spawn(self.voice_loop)
        return self.read_metrics()

    @staticmethod
    def read_metrics():
        return {'cpu': psutil.cpu_percent(interval=None), 'ram': psutil.virtual_memory().percent}

    def process_command(self, command):
        if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_LENGTH:
            return 'Enter a command of 1 to 4,000 characters, Sir.'
        with self.turn:
            return self.run_turn(command.strip())

    def device_action(self, action, value=None):
        if not isinstance(action, str) or action not in DEVICE_ACTIONS:
            return {'error': 'Choose an available device action.'}
        with self.turn:
            self.state('PROCESSING...')
            try:
                result = self.worker.apply(run_device_action, (action, value))
            except DeviceError as error:
                return {'error': str(error)}
            finally:
                self.state('ONLINE')
        if action == 'camera-sources':
            return {'sources': result}
        return {'message': result}

    def network_report(self, report):
        if not isinstance(report, str) or report not in REPORTS:
            return {'error': 'Choose an available local network report.'}
        with self.turn:
            try:
                return {'text': self.worker.apply(read_network_report, (report,))}
            except DiagnosticError as error:
                return {'error': str(error)}

    def hud_info(self):
        return {'model': self.chat.model, 'profile': self.chat.profile,
                'provider': 'Gemini', 'version': APP_VERSION}

    def set_model_profile(self, profile):
        if not isinstance(profile, str) or profile not in self.chat.models:
            return {'error': 'Choose Fast or Deep.'}
        with self.turn:
            self.chat.profile = profile
            return self.hud_info()

    @staticmethod
    def business_site():
        return {'name': STUDIO_NAME, 'url': STUDIO_URL}

    def create_draft(self, command, brief):
        if not isinstance(command, str) or (command != '/studio' and command not in DRAFT_INSTRUCTIONS):
            return {'error': 'Choose a workspace draft command.'}
        if not isinstance(brief, str) or not brief.strip() or len(brief) > MAX_COMMAND_LENGTH:
            return {'error': 'Enter a brief of 1 to 4,000 characters.'}
        if command == '/studio':
            return {'text': studio_update_prompt(brief)}
        if not self.chat.key:
            return {'error': 'Set GEMINI_API_KEY and restart to create drafts.'}
        with self.turn:
            self.state('THINKING...')
            try:
                text = self.worker.apply(self.chat.draft, (command, brief.strip()))
                if command == '/app':
                    text = re.sub(r'^```(?:html)?\s*|\s*```$', '', text, flags=re.IGNORECASE)
                    if not re.match(r'\s*(?:<!doctype html\s*>\s*)?<html(?:\s|>)', text, re.IGNORECASE):
                        return {'error': 'The model did not return a standalone HTML document.'}
                    if not re.search(r'</html>\s*$', text, re.IGNORECASE):
                        return {'error': 'The HTML draft was incomplete.'}
                return {'text': text} if text else {'error': 'Gemini returned an empty draft.'}
            except Exception:
                model_option = 'GEMINI_CODING_MODEL' if self.chat.profile == 'deep' else 'GEMINI_MODEL'
                return {'error': f'JARVIS could not create the draft. Check your Gemini key and {model_option}.'}
            finally:
                self.state('ONLINE')

    def run_turn(self, command):
        normalized = ' '.join(command.casefold().split()).rstrip('?!.,')
        try:
            if normalized in TIME_COMMANDS:
                reply = f'The local time is {datetime.now():%H:%M}, Sir.'
            elif normalized in STATUS_COMMANDS:
                stats = self.read_metrics()
                reply = f'CPU load is {stats["cpu"]:.1f} percent. RAM usage is {stats["ram"]:.1f} percent, Sir.'
            elif not self.chat.key:
                reply = 'Set GEMINI_API_KEY and restart to enable Gemini, Sir.'
            else:
                self.state('THINKING...')
                try:
                    reply = self.worker.apply(self.chat.reply, (command,))
                except Exception:
                    reply = 'I could not reach Gemini, Sir. Check your connection and API setup.'
            if self.voice_enabled:
                self.state('SPEAKING', f'JARVIS: {reply}')
                try:
                    self.worker.apply(self.speak, (reply,))
                except Exception:
                    self.voice_enabled = False
                    self.state('ONLINE', 'Voice playback unavailable. Text replies will continue.')
            return reply
        finally:
            self.state('ONLINE')

    def speak(self, text):
        if self.engine is None:
            import pyttsx3

            self.engine = pyttsx3.init()
        self.engine.say(text)
        self.engine.runAndWait()

    def listen_once(self):
        """Listen once with the local recogniser and return the transcript.

        The microphone is only opened when the owner has allowed it. An empty
        string means that nothing was said, or that the owner closed the
        microphone while it was listening.
        """
        if self.recognizer is None or not self.consent.listening:
            return ''
        try:
            transcript = self.recognizer.recognize_once(LISTEN_TIMEOUT_SECONDS)
        except voice_error():
            # The owner closed the microphone while it was listening.
            return ''
        return str(transcript or '')

    def close_recognizer(self):
        """Close the microphone. The permission of the owner is not touched."""
        if self.recognizer is None:
            return
        try:
            self.recognizer.stop()
        except Exception:
            pass

    def stop_microphone(self):
        """Close the microphone. Only the owner may close it from the HUD."""
        self.consent.stop()
        return {'state': self.consent.listener}

    def voice_loop(self):
        if not self.consent.listening:
            self.mic_enabled = False
            self.voice_loop_started = False
            self.state('ONLINE', 'The microphone is closed. ' + LOCAL_RECOGNITION_NOTE)
            return
        while self.mic_enabled and self.consent.listening:
            with self.turn:
                self.state('LISTENING...')
                try:
                    command = self.worker.apply(self.listen_once).strip()[:MAX_COMMAND_LENGTH]
                except Exception:
                    self.mic_enabled = False
                    self.close_recognizer()
                    self.state(
                        'ONLINE',
                        'Microphone stopped. Check the Windows speech pack, the microphone '
                        'permission and the language.',
                    )
                else:
                    if command:
                        self.state('ACTIVE', f'YOU (VOICE): {command}')
                        speak_reply = self.voice_enabled
                        reply = self.run_turn(command)
                        if not speak_reply:
                            self.state('ONLINE', f'JARVIS: {reply}')
                finally:
                    self.state('ONLINE')
            eel.sleep(0.15)
        self.close_recognizer()
        self.voice_loop_started = False
        if self.mic_enabled:
            self.state('ONLINE', 'The microphone is closed. Nothing is recorded.')


def loopback_app(port):
    app = Bottle()
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

    @app.hook('before_request')
    def require_local_page():
        host = request.headers.get('Host', '').lower()
        if host not in allowed_hosts:
            abort(403, 'Use the local Quantum Core address.')
        if request.path == '/eel' and request.headers.get('Origin') != f'http://{host}':
            abort(403, 'Open Quantum Core from the same local address.')

    return app


def main():
    parser = argparse.ArgumentParser(description='Run the J.A.R.V.I.S. Quantum Core HUD.')
    parser.add_argument(
        '--listen', action='store_true',
        help='Ask for the microphone and listen with the local Windows recogniser.')
    parser.add_argument('--language', default='en-US', help='Speech recognition locale, e.g. ta-IN or fr-FR.')
    parser.add_argument('--no-voice', action='store_true', help='Show text without text-to-speech.')
    parser.add_argument('--browser', choices=('chrome', 'edge', 'none'), default='chrome')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')

    key = os.environ.get('GEMINI_API_KEY', '').strip()
    chat = GeminiChat(
        key, os.environ.get('GEMINI_MODEL', '').strip() or MODEL,
        os.environ.get('GEMINI_CODING_MODEL', '').strip() or DEEP_MODEL,
    )
    consent = voice_layer('consent').VoiceConsent()
    recognizer = None
    listening = args.listen
    if args.listen:
        try:
            recognizer = local_recognizer(consent, args.language)
        except voice_error() as error:
            # There is no cloud service to fall back to, so the microphone stays
            # closed and the owner is told plainly why.
            print('The microphone stays closed: ' + str(error))
            recognizer = None
            listening = False
        if recognizer is not None and not ask_for_microphone(consent):
            listening = False
    hud = QuantumCore(chat, speak=not args.no_voice, listen=listening,
                      language=args.language, consent=consent, recognizer=recognizer)

    def resume_voice():
        """The owner asked for the microphone again in the terminal."""
        hud.mic_enabled = True
        hud.voice_loop_started = False

    if listening:
        # The owner may take the microphone back from the same terminal.
        watch_for_stop(consent, on_resume=resume_voice)
    # Prime psutil's nonblocking CPU counter before the first browser poll.
    psutil.cpu_percent(interval=None)
    eel.init(str(Path(__file__).resolve().parent / 'web'))
    eel.expose('get_system_stats')(hud.system_metrics)
    eel.expose('hud_info')(hud.hud_info)
    eel.expose('set_model_profile')(hud.set_model_profile)
    eel.expose('process_jarvis_command')(hud.process_command)
    eel.expose('create_draft')(hud.create_draft)
    eel.expose('device_action')(hud.device_action)
    eel.expose('network_report')(hud.network_report)
    eel.expose('business_site')(hud.business_site)
    # The HUD page may close the microphone. It may never open it: only the
    # owner, in the terminal, can allow the microphone.
    eel.expose('stop_microphone')(hud.stop_microphone)
    eel.start(
        'index.html', host='127.0.0.1', port=args.port,
        mode=None if args.browser == 'none' else args.browser, size=(1366, 768),
        app=loopback_app(args.port),
    )


if __name__ == '__main__':
    main()
