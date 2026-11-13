"""Offline tests for explicit speech text preparation."""
import unittest
from desktop.speech import speech_text


class SpeechTextTests(unittest.TestCase):
    def test_trims_and_limits_text(self):
        self.assertEqual(speech_text("  hello  "), "hello")
        self.assertEqual(len(speech_text("x" * 5000)), 2500)

    def test_non_text_rejected(self):
        with self.assertRaises(TypeError):
            speech_text(None)


if __name__ == "__main__":
    unittest.main()
