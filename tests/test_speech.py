"""Offline tests for explicit speech text preparation."""
import unittest
from desktop.speech import speech_text, speech_chunks


class SpeechTextTests(unittest.TestCase):
    def test_trims_and_limits_text(self):
        self.assertEqual(speech_text("  hello  "), "hello")
        self.assertEqual(len(speech_text("x" * 5000)), 2500)

    def test_chunks_preserve_words_and_length(self):
        text = 'Tamil English French local speech output'
        chunks = speech_chunks(text, max_chars=14)
        self.assertEqual(' '.join(chunks), text)
        self.assertTrue(all(len(chunk) <= 14 for chunk in chunks))

    def test_long_word_is_split(self):
        self.assertEqual(speech_chunks('abcdefghij', max_chars=4), ['abcd', 'efgh', 'ij'])

    def test_non_text_rejected(self):
        with self.assertRaises(TypeError):
            speech_text(None)


if __name__ == "__main__":
    unittest.main()
