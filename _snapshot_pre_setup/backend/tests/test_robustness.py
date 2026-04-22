import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.robustness import sensitivity_grid, walk_forward_backtest


class TestRobustness(unittest.TestCase):
    def test_walk_forward(self):
        eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(entry_mode="none"))
        r = walk_forward_backtest(eng, symbol="TEST", provider="csv", base_timeframe="1h", segments=2, min_rows=40)
        self.assertIn("segments", r)

    def test_sensitivity(self):
        r = sensitivity_grid(
            data_dir=settings.DATA_DIR,
            symbol="TEST",
            provider="csv",
            base_timeframe="1h",
            csv_path=None,
            grid={"adx_threshold": [15.0, 18.0], "alignment_threshold": [0.6]},
            max_rows=10,
        )
        self.assertIn("results", r)


if __name__ == "__main__":
    unittest.main()
