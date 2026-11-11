"""Offline tests for the unified provider selection policy."""
import unittest

from unified_provider_policy import NoProviderAvailable, Provider, choose_provider


class ProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.providers = (
            Provider("openai", configured=True, healthy=False),
            Provider("gemini", configured=True, healthy=True),
            Provider("ollama", configured=True, healthy=True, local=True),
        )

    def test_no_implicit_fallback(self):
        with self.assertRaises(NoProviderAvailable):
            choose_provider(self.providers, "openai")

    def test_explicit_fallback(self):
        self.assertEqual(
            choose_provider(self.providers, "openai", allow_fallback=True).name,
            "gemini",
        )

    def test_offline_selects_local(self):
        self.assertEqual(
            choose_provider(self.providers, "openai", allow_fallback=True, offline_only=True).name,
            "ollama",
        )

    def test_offline_rejects_remote(self):
        with self.assertRaises(NoProviderAvailable):
            choose_provider(self.providers, "gemini", offline_only=True)

    def test_unknown_preference_rejected(self):
        with self.assertRaises(ValueError):
            choose_provider(self.providers, "nonexistent", allow_fallback=True)

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            choose_provider((Provider("x", True, True), Provider("x", True, True)), "x")

    def test_unconfigured_provider_rejected(self):
        with self.assertRaises(NoProviderAvailable):
            choose_provider((Provider("ollama", False, True, local=True),), "ollama")


if __name__ == "__main__":
    unittest.main()
