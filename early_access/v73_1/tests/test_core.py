import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import provider_statuses, ollama_chat, require_owner_approval, ollama_health

class CoreTests(unittest.TestCase):
    def test_provider_count(self):
        self.assertEqual(len(provider_statuses({})), 4)
    def test_cloud_unconfigured(self):
        self.assertFalse(provider_statuses({})[1].configured)
    def test_cloud_configured(self):
        self.assertTrue(provider_statuses({'OPENAI_API_KEY':'example'})[1].configured)
    def test_reject_external_endpoint(self):
        with self.assertRaises(ValueError): ollama_chat('hello', endpoint='https://example.com')
    def test_reject_empty_prompt(self):
        with self.assertRaises(ValueError): ollama_chat(' ')
    def test_reject_oversize_prompt(self):
        with self.assertRaises(ValueError): ollama_chat('x' * 8001)
    def test_reject_bad_model(self):
        with self.assertRaises(ValueError): ollama_chat('hi', model='a/b')
    def test_approval_default_denied(self):
        self.assertFalse(require_owner_approval('run_code', False))
    def test_approval_true(self):
        self.assertTrue(require_owner_approval('run_code', True))
    def test_unknown_action(self):
        with self.assertRaises(ValueError): require_owner_approval('delete_everything', True)
    def test_mock_ollama(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"message":{"content":"Vanakkam!"}}'
        with patch('urllib.request.urlopen', return_value=FakeResponse()) as mock:
            self.assertEqual(ollama_chat('Vanakkam'), 'Vanakkam!')
            self.assertIn('127.0.0.1', mock.call_args.args[0].full_url)

class HealthTests(unittest.TestCase):
    def test_health_rejects_remote_endpoint(self):
        with self.assertRaises(ValueError): ollama_health('https://example.com')
    def test_health_offline(self):
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertFalse(ollama_health())
    def test_health_valid(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"models":[]}'
        with patch('urllib.request.urlopen', return_value=Response()):
            self.assertTrue(ollama_health())
    def test_health_invalid(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return b'{"not_models":[]}'
        with patch('urllib.request.urlopen', return_value=Response()):
            self.assertFalse(ollama_health())

if __name__ == '__main__': unittest.main()
