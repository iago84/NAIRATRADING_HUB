import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.execution_gates import timing_gate


class TestTimingGate(unittest.TestCase):
    def test_expansion_blocks_age(self):
        d = timing_gate(trend_age_bars=3, ema_compression=1.0)
        self.assertFalse(d.ok)
        self.assertIn("gate_timing_age", d.reasons)

    def test_expansion_blocks_compression(self):
        d = timing_gate(trend_age_bars=1, ema_compression=2.0)
        self.assertFalse(d.ok)
        self.assertIn("gate_timing_compression", d.reasons)


if __name__ == "__main__":
    unittest.main()

