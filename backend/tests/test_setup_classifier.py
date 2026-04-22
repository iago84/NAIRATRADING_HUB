import unittest
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.setup_classifier import classify_setups


class TestSetupClassifier(unittest.TestCase):
    def test_returns_candidates_sorted(self):
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2025-01-01", periods=5, freq="1h"),
                "open": [100, 101, 102, 103, 104],
                "high": [101, 102, 103, 104, 110],
                "low": [99, 100, 101, 102, 90],
                "close": [101, 102, 103, 104, 105],
                "atr": [1, 1, 1, 1, 1],
                "ema_25": [100, 101, 102, 103, 104],
                "ema_80": [99, 100, 101, 102, 103],
                "ema_compression": [1, 1, 1, 1, 1],
                "adx": [10, 10, 10, 10, 10],
                "alignment": [1, 1, 1, 1, 1],
                "trend_age_bars": [1, 1, 1, 1, 1],
                "curvature": [0, 0, 0, 0, 0],
                "slope_score": [0, 0, 0, 0, 0],
                "regression_r2": [1, 1, 1, 1, 1],
            }
        )
        frames = [{"timeframe": "1h", "level_confluence_score": 0.5, "direction": "buy"}]
        r = classify_setups(df_feat_base=df, frames=frames, base_timeframe="1h")
        self.assertIn("setup_primary", r)
        self.assertTrue(isinstance(r["setup_primary"], str))
        c = r.get("setup_candidates") or []
        self.assertGreaterEqual(len(c), 1)
        scores = [float(x.get("score") or 0.0) for x in c]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()

