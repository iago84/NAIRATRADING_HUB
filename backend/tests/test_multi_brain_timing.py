import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.multi_brain import run_multi_brain
from app.engine.naira_engine import NairaEngine


class TestMultiBrainTiming(unittest.TestCase):
    def test_timing_gate_blocks(self):
        orig = {
            "CONFLUENCE_MIN": settings.CONFLUENCE_MIN,
            "STRUCT_ALIGN_4H_MIN": settings.STRUCT_ALIGN_4H_MIN,
            "STRUCT_ALIGN_1D_MIN": settings.STRUCT_ALIGN_1D_MIN,
            "TIMING_MODE": settings.TIMING_MODE,
            "EXPANSION_MAX_TREND_AGE": settings.EXPANSION_MAX_TREND_AGE,
            "EXPANSION_MAX_EMA_COMPRESSION": settings.EXPANSION_MAX_EMA_COMPRESSION,
        }
        try:
            object.__setattr__(settings, "CONFLUENCE_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_4H_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_1D_MIN", 0.0)
            object.__setattr__(settings, "TIMING_MODE", "expansion")
            object.__setattr__(settings, "EXPANSION_MAX_TREND_AGE", 2)
            object.__setattr__(settings, "EXPANSION_MAX_EMA_COMPRESSION", 1.5)

            e = NairaEngine(data_dir=settings.DATA_DIR)
            out, _ = run_multi_brain(engine=e, symbol="TEST", provider="csv", base_timeframe="1h", tranche="T0", include_debug=True)
            self.assertEqual(out.get("direction"), "neutral")
            self.assertIn("gate_timing_compression", list(out.get("reasons") or []))
        finally:
            for k, v in orig.items():
                object.__setattr__(settings, k, v)


if __name__ == "__main__":
    unittest.main()

