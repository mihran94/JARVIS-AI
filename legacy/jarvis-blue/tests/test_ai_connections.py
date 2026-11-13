import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core.codex_bridge import review_command, review_prompt
from providers.llm_openai import CATALOG, OpenAICompatLLM
from providers import registry


class ConnectionTests(unittest.TestCase):
    def test_each_service_uses_its_own_endpoint_and_key(self):
        import httpx
        real_client = httpx.Client
        for service in ('gemini', 'openai', 'minimax'):
            entry = next(item for item in CATALOG if item['id'] == service)
            cfg = dict(entry['values'], api_key=f'test-{service}', model='test-model')
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}}]})
            transport = httpx.MockTransport(handler)
            with patch('httpx.Client', side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
                client = OpenAICompatLLM(cfg)
                self.assertEqual(client.complete([{'role': 'user', 'content': 'test'}])[0], 'ok')
            self.assertEqual(str(requests[0].url), entry['values']['base_url'] + '/chat/completions')
            self.assertEqual(requests[0].headers['Authorization'], f'Bearer test-{service}')
            self.assertEqual(json.loads(requests[0].content)['model'], 'test-model')

    def test_all_hosted_services_require_keys(self):
        for service in ('gemini', 'openai', 'minimax'):
            self.assertIn('API key', registry.missing_fields('openai_compat@' + service, {'model': 'example', 'base_url': 'https://example.com'}))

    def test_codex_command_uses_readonly_and_stdin(self):
        with tempfile.TemporaryDirectory(prefix='project space ') as root:
            cmd = review_command(root, '/usr/bin/codex')
            self.assertEqual(cmd[-1], '-')
            self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'read-only')
            self.assertEqual(cmd[cmd.index('--ask-for-approval') + 1], 'never')
            self.assertIn('--ignore-user-config', cmd)
            self.assertIn(str(Path(root).resolve()), cmd)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)

    def test_missing_cli_and_invalid_directory(self):
        with tempfile.TemporaryDirectory() as root, patch('core.codex_bridge.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'not installed'):
                review_command(root)
            with self.assertRaises(OSError):
                review_command(Path(root) / 'absent', '/usr/bin/codex')

    def test_windows_npm_shim_without_shell(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            script = base / 'node_modules/@openai/codex/bin/codex.js'
            script.parent.mkdir(parents=True)
            script.touch()
            with patch('core.codex_bridge.shutil.which', return_value='node.exe'):
                cmd = review_command(root, str(base / 'codex.cmd'))
            self.assertEqual(cmd[:2], ['node.exe', str(script)])
            self.assertNotIn('cmd.exe', cmd)

    def test_prompt_is_not_a_shell_command(self):
        self.assertIn('$(echo test)', review_prompt('Review $(echo test)'))
        for request in (' ', 'x' * 16001):
            with self.assertRaises(ValueError):
                review_prompt(request)
