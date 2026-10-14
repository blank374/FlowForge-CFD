"""A failed import must remain readable and must not release later stages."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.app import run_stages


class StageStatusTest(unittest.TestCase):
    def test_missing_geometry_summary_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run_summary.json").write_text(
                json.dumps({"status": "failed", "geometry": None, "stages": []}), encoding="utf-8")
            stages = run_stages({"kind": "l1_full", "status": "failed"}, root)
        self.assertEqual(len(stages), 7)
        self.assertTrue(all(stage["status"] == "BLOCKED" for stage in stages))


if __name__ == "__main__":
    unittest.main()
