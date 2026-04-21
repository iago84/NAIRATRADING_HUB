import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.multi_brain import run_multi_brain
from app.engine.naira_engine import NairaEngine


class TestMultiBrainSignal(unittest.TestCase):
    def test_multi_brain_signal_smoke(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        out, meta = run_multi_brain(engine=e, symbol="TEST", provider="csv", base_timeframe="1h", tranche="T0", include_debug=True)
        self.assertIn(out.get("direction"), ("buy", "sell", "neutral"))
        dbg = out.get("debug") or {}
        self.assertIn(dbg.get("regime"), ("trend", "range", "transition"))


if __name__ == "__main__":
    unittest.main()
