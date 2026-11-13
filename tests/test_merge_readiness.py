"""Tests for the structural consolidation gate."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_merge_readiness import REQUIRED, missing_sources


class MergeReadinessTests(unittest.TestCase):
    def test_missing_sources_block_merge(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(len(missing_sources(Path(tmp))), len(REQUIRED))

    def test_empty_directories_do_not_count(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in REQUIRED.values():
                (root / relative).mkdir(parents=True, exist_ok=True)
            self.assertEqual(len(missing_sources(root)), len(REQUIRED))

    def test_present_directories_pass_structural_check(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in REQUIRED.values():
                folder = root / relative
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "source.txt").write_text("test fixture")
            self.assertEqual(missing_sources(root), [])


if __name__ == "__main__":
    unittest.main()
