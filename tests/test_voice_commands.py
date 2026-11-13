"""Pure offline voice-command tests; never launch applications."""
import unittest
from desktop.voice_commands import parse_voice_command


class VoiceCommandTests(unittest.TestCase):
    def test_allowlisted_exact_commands(self):
        self.assertEqual(parse_voice_command("Open Notepad!"), "Notepad")
        self.assertEqual(parse_voice_command(" launch   calculator "), "Calculator")

    def test_rejects_extra_or_dangerous_instructions(self):
        for value in ("open notepad and delete files", "cmd.exe", "open calculator; shutdown",
                      "please open notepad", "", None, "open powershell"):
            with self.subTest(value=value):
                self.assertIsNone(parse_voice_command(value))


if __name__ == "__main__":
    unittest.main()
