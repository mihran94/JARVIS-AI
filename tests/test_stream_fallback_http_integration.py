"""Offline HTTP integration tests: no real API keys or network requests."""
import unittest
import httpx
from providers.chat import ProviderError, stream_chat
from providers.stream_fallback import StreamTarget, FallbackBlocked, stream_with_fallback

PRIMARY = StreamTarget("OpenAI", "test-model", "fake-key")
BACKUP = StreamTarget("Gemini", "test-model", "fake-backup-key")
MESSAGES = [{"role": "user", "content": "offline test"}]
SSE = (b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
       b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
       b'data: [DONE]\n\n')

class HttpFallbackIntegrationTests(unittest.TestCase):
    def run_case(self, consent, handler):
        requests = []
        def record(request):
            requests.append(str(request.url))
            return handler(request)
        transport = httpx.MockTransport(record)
        def stream(provider, model, key, messages, check, emit):
            return stream_chat(provider, model, key, messages, check, emit,
                               transport=transport)
        chunks = []
        def execute():
            return stream_with_fallback(
                PRIMARY, BACKUP, MESSAGES, lambda: None, chunks.append,
                stream, consent_to_backup=consent,
                retryable_errors=(ProviderError,))
        return execute, requests, chunks

    def test_no_consent_blocks_backup_request(self):
        execute, requests, chunks = self.run_case(
            False, lambda request: httpx.Response(503))
        with self.assertRaises(FallbackBlocked):
            execute()
        self.assertEqual(len(requests), 1)
        self.assertEqual(chunks, [])

    def test_explicit_consent_uses_backup_after_primary_503(self):
        def handler(request):
            if "api.openai.com" in str(request.url):
                return httpx.Response(503)
            return httpx.Response(200, content=SSE)
        execute, requests, chunks = self.run_case(True, handler)
        self.assertEqual(execute(), ("Gemini", "ok"))
        self.assertEqual(len(requests), 2)
        self.assertEqual(chunks, ["ok"])

    def test_successful_primary_never_calls_backup(self):
        execute, requests, chunks = self.run_case(
            True, lambda request: httpx.Response(200, content=SSE))
        self.assertEqual(execute(), ("OpenAI", "ok"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(chunks, ["ok"])

if __name__ == "__main__":
    unittest.main()
