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
        frames = [{"timeframe": "1h", "level_confluence_score": 0.1}]
        r = confluence_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_low_confluence", r.reasons)

    def test_exec_threshold_blocks(self):
        frames = [{"timeframe": "1h", "confidence": 0.6, "alignment": 0.6}]
        r = execution_threshold_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_execution_threshold", r.reasons)


if __name__ == "__main__":
    unittest.main()

