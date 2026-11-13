"""Offline checks for the monorepo source import plan."""
import unittest
from scripts.import_jarvis_sources import SOURCES, commands, main


class SourceImportTests(unittest.TestCase):
    def test_all_three_separate_upstreams(self):
        self.assertEqual(len(SOURCES), 3)
        self.assertEqual({item[0] for item in SOURCES},
                         {"legacy/jarvis-blue", "android", "legacy/jarvis-mobile-beta"})

    def test_import_uses_subtree_and_no_destructive_operations(self):
        planned = commands()
        self.assertEqual(len(planned), 3)
        for cmd in planned:
            self.assertEqual(cmd[:3], ["git", "subtree", "add"])
            self.assertNotIn("--squash", cmd)
            self.assertNotIn("push", cmd)
            self.assertNotIn("delete", cmd)

    def test_select_one_source(self):
        selected = commands('android')
        self.assertEqual(len(selected), 1)
        self.assertIn('--prefix=android', selected[0])
        self.assertNotIn('legacy/jarvis-blue', ' '.join(selected[0]))

    def test_mobile_beta_source_is_separate_and_history_preserving(self):
        selected = commands('legacy/jarvis-mobile-beta')
        self.assertEqual(len(selected), 1)
        self.assertIn('--prefix=legacy/jarvis-mobile-beta', selected[0])
        self.assertIn('mihran94/JARVIS-Mobile-Beta.git', selected[0])
        self.assertNotIn('--squash', selected[0])

    def test_one_source_dry_run(self):
        self.assertEqual(main(['--source', 'android']), 0)

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            commands('unexpected-repository')

    def test_import_command_never_targets_main_repository(self):
        for command in commands():
            self.assertNotIn('JARVIS-AI.git', ' '.join(command))
            self.assertEqual(command[0:3], ['git', 'subtree', 'add'])

    def test_default_is_dry_run(self):
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
