import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.ensemble import combine
from app.engine.brains.types import BrainSignal


class TestEnsemble(unittest.TestCase):
    def test_agree_bonus(self):
        dom = BrainSignal(brain="trend", direction="buy", confidence=0.6, opportunity_score=50.0, reasons=["a"], risk={}, ai_p_win=None)
        sec = BrainSignal(brain="pullback", direction="buy", confidence=0.6, opportunity_score=50.0, reasons=["b"], risk={}, ai_p_win=None)
        out = combine(dom, sec)
        self.assertGreater(out.confidence, dom.confidence)
        self.assertIn("ensemble=agree", out.reasons)

    def test_disagree_penalty(self):
        dom = BrainSignal(brain="trend", direction="buy", confidence=0.6, opportunity_score=50.0, reasons=["a"], risk={}, ai_p_win=None)
        sec = BrainSignal(brain="breakout", direction="sell", confidence=0.6, opportunity_score=50.0, reasons=["b"], risk={}, ai_p_win=None)
        out = combine(dom, sec)
        self.assertLess(out.confidence, dom.confidence)
        self.assertIn("ensemble=disagree", out.reasons)


if __name__ == "__main__":
    unittest.main()
