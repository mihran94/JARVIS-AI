"""Offline validation tests; no microphone opened."""
import tempfile
import unittest
from pathlib import Path
from desktop.dictation import validate_model_path, normalize_transcript


class DictationTests(unittest.TestCase):
    def test_transcript_normalization(self):
        self.assertEqual(normalize_transcript(['  hello ', '', ' world  ']), 'hello world')
        self.assertEqual(normalize_transcript([' ']), '')
        self.assertEqual(normalize_transcript(['abcdefgh'], max_chars=4), 'abcd')
        with self.assertRaises(ValueError):
            normalize_transcript(['hello'], max_chars=0)

    def test_reject_blank_model_path(self):
        for path in ('', '   ', None):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_model_path(path)

    def test_reject_missing_model(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                validate_model_path(root)

    def test_accept_extracted_model_structure(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "am").mkdir()
            (Path(root) / "conf").mkdir()
            self.assertEqual(validate_model_path(root), root)

    def test_reject_nonexistent_model(self):
        with self.assertRaises(ValueError):
            validate_model_path("/unlikely-jarvis-model-path-not-found")


if __name__ == "__main__":
    unittest.main()
