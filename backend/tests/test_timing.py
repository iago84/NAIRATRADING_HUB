import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.timing import trend_age_bars_from_directions


class TestTiming(unittest.TestCase):
    def test_trend_age_counts_run(self):
        self.assertEqual(trend_age_bars_from_directions(["buy", "buy", "buy"]), 3)
        self.assertEqual(trend_age_bars_from_directions(["buy", "buy", "sell"]), 1)
        self.assertEqual(trend_age_bars_from_directions(["neutral", "buy", "buy"]), 2)

    def test_trend_age_neutral_zero(self):
        self.assertEqual(trend_age_bars_from_directions(["buy", "buy", "neutral"]), 0)


if __name__ == "__main__":
    unittest.main()

