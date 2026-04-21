import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.regime_router import classify_regime, pick_brains


class TestRegimeRouter(unittest.TestCase):
    def test_trend(self):
        frames = [{"timeframe": "4h", "adx": 25.0, "ema_compression": 2.0, "slope_score": 0.2}]
        self.assertEqual(classify_regime(frames), "trend")
        self.assertEqual(pick_brains("trend").dominant, "trend")

    def test_range(self):
        frames = [{"timeframe": "4h", "adx": 10.0, "ema_compression": 5.0, "slope_score": 0.01}]
        self.assertEqual(classify_regime(frames), "range")
        self.assertEqual(pick_brains("range").dominant, "mean_reversion")

    def test_transition(self):
        frames = [{"timeframe": "4h", "adx": 16.0, "ema_compression": 3.1, "slope_score": 0.02}]
        self.assertEqual(classify_regime(frames), "transition")
        self.assertEqual(pick_brains("transition").dominant, "breakout")


if __name__ == "__main__":
    unittest.main()
