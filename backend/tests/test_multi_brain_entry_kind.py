import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.multi_brain import run_multi_brain
from app.engine.naira_engine import NairaEngine


class TestMultiBrainEntryKind(unittest.TestCase):
    def test_multi_brain_sets_entry_kind(self):
        orig = {
            "CONFLUENCE_MIN": settings.CONFLUENCE_MIN,
            "STRUCT_ALIGN_4H_MIN": settings.STRUCT_ALIGN_4H_MIN,
            "STRUCT_ALIGN_1D_MIN": settings.STRUCT_ALIGN_1D_MIN,
            "EXPANSION_MAX_TREND_AGE": settings.EXPANSION_MAX_TREND_AGE,
            "EXPANSION_MAX_EMA_COMPRESSION": settings.EXPANSION_MAX_EMA_COMPRESSION,
        }
        try:
            object.__setattr__(settings, "CONFLUENCE_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_4H_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_1D_MIN", 0.0)
            object.__setattr__(settings, "EXPANSION_MAX_TREND_AGE", 999)
            object.__setattr__(settings, "EXPANSION_MAX_EMA_COMPRESSION", 999.0)

            e = NairaEngine(data_dir=settings.DATA_DIR)
            out, _ = run_multi_brain(engine=e, symbol="TEST", provider="csv", base_timeframe="1h", tranche="T0", include_debug=True)
            self.assertIn("entry_kind", out)
            self.assertTrue(isinstance(out.get("entry_kind"), str))
            self.assertNotEqual(out.get("entry_kind"), "")
        finally:
            for k, v in orig.items():
                object.__setattr__(settings, k, v)


if __name__ == "__main__":
    unittest.main()
