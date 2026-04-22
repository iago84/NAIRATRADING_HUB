import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


class TestBacktestTimingGate(unittest.TestCase):
    def test_backtest_timing_gate_counts(self):
        orig = {
            "CONFLUENCE_MIN": settings.CONFLUENCE_MIN,
            "STRUCT_ALIGN_4H_MIN": settings.STRUCT_ALIGN_4H_MIN,
            "STRUCT_ALIGN_1D_MIN": settings.STRUCT_ALIGN_1D_MIN,
            "EXEC_CONF_MIN": settings.EXEC_CONF_MIN,
            "EXEC_ALIGN_MIN": settings.EXEC_ALIGN_MIN,
            "TIMING_MODE": settings.TIMING_MODE,
            "EXPANSION_MAX_TREND_AGE": settings.EXPANSION_MAX_TREND_AGE,
            "EXPANSION_MAX_EMA_COMPRESSION": settings.EXPANSION_MAX_EMA_COMPRESSION,
        }
        try:
            object.__setattr__(settings, "CONFLUENCE_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_4H_MIN", 0.0)
            object.__setattr__(settings, "STRUCT_ALIGN_1D_MIN", 0.0)
            object.__setattr__(settings, "EXEC_CONF_MIN", 0.0)
            object.__setattr__(settings, "EXEC_ALIGN_MIN", 0.0)
            object.__setattr__(settings, "TIMING_MODE", "expansion")

            cfg = NairaConfig(
                strategy_mode="multi",
                entry_mode="hybrid",
                confirm_higher_tfs=False,
                timing_timeframe="",
                alignment_threshold=0.0,
                slope_threshold_pct=0.0,
                adx_threshold=0.0,
                min_confidence=0.0,
                trend_age_min_bars=0,
                trend_age_max_bars=999,
                ema_compression_max=999,
            )
            e = NairaEngine(data_dir=settings.DATA_DIR, config=cfg)

            object.__setattr__(settings, "EXPANSION_MAX_TREND_AGE", 0)
            object.__setattr__(settings, "EXPANSION_MAX_EMA_COMPRESSION", 0.0)
            r = e.backtest(symbol="TEST", provider="csv", base_timeframe="1h", max_bars=500)
            met = r.get("metrics") or {}
            self.assertGreater(int(met.get("gates_timing_blocked") or 0), 0)
            self.assertGreater(int(met.get("blocked_timing_gate") or 0), 0)

            object.__setattr__(settings, "EXPANSION_MAX_TREND_AGE", 999)
            object.__setattr__(settings, "EXPANSION_MAX_EMA_COMPRESSION", 999.0)
            r2 = e.backtest(symbol="TEST", provider="csv", base_timeframe="1h", max_bars=500)
            met2 = r2.get("metrics") or {}
            self.assertEqual(int(met2.get("gates_timing_blocked") or 0), 0)
            self.assertEqual(int(met2.get("blocked_timing_gate") or 0), 0)
        finally:
            for k, v in orig.items():
                object.__setattr__(settings, k, v)


if __name__ == "__main__":
    unittest.main()
