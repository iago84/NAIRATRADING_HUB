import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.ai_gate import allow


class TestAIGate(unittest.TestCase):
    def test_allow_none_model(self):
        d = allow(None, "T0")
        self.assertTrue(d.ok)
        self.assertEqual(d.reason, "no_model")

    def test_blocks_below_threshold(self):
        d = allow(0.1, "T0")
        self.assertFalse(d.ok)
        self.assertEqual(d.reason, "below_threshold")


if __name__ == "__main__":
    unittest.main()
