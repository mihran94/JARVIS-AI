"""Regression tests for opt-in fallback: at most one backup attempt."""
import unittest
from providers.stream_fallback import StreamTarget, stream_with_fallback


class BackupSingleAttemptTests(unittest.TestCase):
    def setUp(self):
        self.primary = StreamTarget('OpenAI', 'model-a', 'local-placeholder-a')
        self.backup = StreamTarget('Gemini', 'model-b', 'local-placeholder-b')
        self.messages = [{'role': 'user', 'content': 'test'}]

    def test_backup_failure_does_not_retry_or_attempt_third_provider(self):
        calls = []

        def stream(provider, model, key, messages, check, emit):
            calls.append(provider)
            raise TimeoutError('simulated outage')

        with self.assertRaises(TimeoutError):
            stream_with_fallback(self.primary, self.backup, self.messages,
                                 lambda: None, lambda _: None, stream,
                                 consent_to_backup=True)
        self.assertEqual(calls, ['OpenAI', 'Gemini'])

    def test_backup_receives_original_messages_and_check(self):
        calls = []
        checks = []
        output = []

        def check():
            checks.append('checked')

        def stream(provider, model, key, messages, check, emit):
            calls.append((provider, messages is self.messages))
            check()
            if provider == 'OpenAI':
                raise ConnectionError('simulated outage')
            emit('ok')
            return 'ok'

        result = stream_with_fallback(self.primary, self.backup, self.messages,
                                      check, output.append, stream,
                                      consent_to_backup=True)
        self.assertEqual(result, ('Gemini', 'ok'))
        self.assertEqual(calls, [('OpenAI', True), ('Gemini', True)])
        self.assertEqual(output, ['ok'])
        self.assertGreaterEqual(len(checks), 3)


if __name__ == '__main__':
    unittest.main()
