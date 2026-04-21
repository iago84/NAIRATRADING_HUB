import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.tuner import tune_basic


class TestTuner(unittest.TestCase):
    def test_tune_basic(self):
        r = tune_basic(
            data_dir=settings.DATA_DIR,
            symbol="TEST",
            provider="csv",
            base_timeframe="1h",
            max_iters=10,
            min_trades=1,
            seed=1,
        )
        self.assertIn("best_params", r)
        self.assertIn("best_metrics", r)


if __name__ == "__main__":
    unittest.main()
