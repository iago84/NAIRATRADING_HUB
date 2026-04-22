import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine
from app.engine.multi_brain import run_multi_brain


class TestSetupIntegration(unittest.TestCase):
    def test_analyze_includes_setup(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.analyze(symbol="TEST", provider="csv", base_timeframe="1h")
        self.assertIn("setup_primary", r)
        self.assertIn("setup_candidates", r)

    def test_multi_brain_includes_setup(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r, _ = run_multi_brain(engine=e, symbol="TEST", provider="csv", base_timeframe="1h", tranche="T0")
        self.assertIn("setup_primary", r)
        self.assertIn("setup_candidates", r)


if __name__ == "__main__":
    unittest.main()

