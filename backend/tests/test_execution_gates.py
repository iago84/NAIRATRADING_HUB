import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.execution_gates import structural_gate, confluence_gate, execution_threshold_gate


class TestExecutionGates(unittest.TestCase):
    def test_structural_gate_blocks(self):
        frames = [
            {"timeframe": "4h", "alignment": 0.5},
            {"timeframe": "1d", "alignment": 0.5},
        ]
        r = structural_gate(frames)
        self.assertFalse(r.ok)
        self.assertIn("gate_structural", r.reasons)

    def test_confluence_gate_blocks(self):
        frames = [{"timeframe": "1h", "level_confluence_score": 0.14}]
        r = confluence_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_low_confluence", r.reasons)

    def test_exec_threshold_blocks(self):
        frames = [{"timeframe": "1h", "confidence": 0.59, "alignment": 0.64}]
        r = execution_threshold_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_execution_threshold", r.reasons)

    def test_micro_timeframe_more_permissive(self):
        frames = [{"timeframe": "5m", "level_confluence_score": 0.11, "confidence": 0.56, "alignment": 0.61}]
        r1 = confluence_gate(frames, base_timeframe="5m")
        self.assertTrue(r1.ok)
        r2 = execution_threshold_gate(frames, base_timeframe="5m")
        self.assertTrue(r2.ok)


if __name__ == "__main__":
    unittest.main()
