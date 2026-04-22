import unittest
from pathlib import Path
import sys
import os
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


class TestNairaEngine(unittest.TestCase):
    def test_analyze_from_csv(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.analyze(symbol="TEST", provider="csv", base_timeframe="1h")
        self.assertIn(r["direction"], ("buy", "sell", "neutral"))
        self.assertGreaterEqual(float(r["confidence"]), 0.0)
        self.assertLessEqual(float(r["confidence"]), 1.0)
        self.assertGreaterEqual(float(r["opportunity_score"]), 0.0)
        self.assertLessEqual(float(r["opportunity_score"]), 100.0)
        self.assertTrue(isinstance(r["frames"], list))
        if r["frames"]:
            f0 = r["frames"][-1]
            self.assertIn("regression_slope_pct", f0)
            self.assertIn("regression_r2", f0)
        self.assertIn("valid_until", r["risk"])
        self.assertIn("ttl_bars", r["risk"])

    def test_analyze_includes_trend_age_bars(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.analyze(symbol="TEST", provider="csv", base_timeframe="1h")
        f = None
        for fr in r.get("frames") or []:
            if str(fr.get("timeframe") or "") == "1h":
                f = fr
                break
        self.assertIsNotNone(f)
        self.assertIn("trend_age_bars", f)
        self.assertGreaterEqual(int(f.get("trend_age_bars") or 0), 0)

    def test_backtest_from_csv(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.backtest(symbol="TEST", provider="csv", base_timeframe="1h")
        self.assertIn("metrics", r)
        self.assertIn("trades", r)
        if r.get("trades"):
            t0 = r["trades"][0]
            self.assertIn("entry_kind", t0)
            self.assertIn("exit_reason", t0)

    def test_backtest_multi_strategy_mode(self):
        cfg = NairaConfig(
            strategy_mode="multi",
            entry_mode="hybrid",
            confirm_higher_tfs=False,
            timing_timeframe="",
            alignment_threshold=0.0,
            slope_threshold_pct=0.0,
            adx_threshold=0.0,
            min_confidence=0.0,
        )
        e = NairaEngine(data_dir=settings.DATA_DIR, config=cfg)
        r = e.backtest(symbol="TEST", provider="csv", base_timeframe="1h", max_bars=500)
        self.assertIn("metrics", r)
        self.assertIn("trades", r)

    def test_backtest_money_management_and_signal_stats(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.backtest(
            symbol="TEST",
            provider="csv",
            base_timeframe="1h",
            starting_cash=10000.0,
            sizing_mode="fixed_risk",
            risk_per_trade_pct=1.0,
            max_leverage=1.0,
            collect_signal_stats=True,
        )
        self.assertIn("metrics", r)
        met = r.get("metrics") or {}
        self.assertIn("signals_raw_total", met)
        self.assertIn("signals_entry_total", met)

    def test_backtest_bar_magnifier_from_csv(self):
        import pandas as pd
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            base_dir = td
            sym_dir = Path(base_dir) / "history" / "csv" / "TEST"
            os.makedirs(sym_dir, exist_ok=True)

            start = pd.Timestamp("2025-01-01T00:00:00Z")
            n_base = 90
            base_times = pd.date_range(start=start, periods=n_base, freq="1h")
            base_close = np.linspace(100.0, 140.0, num=n_base)
            base_open = np.roll(base_close, 1)
            base_open[0] = base_close[0]
            base_high = np.maximum(base_open, base_close) + 0.5
            base_low = np.minimum(base_open, base_close) - 0.5
            df_1h = pd.DataFrame(
                {
                    "datetime": base_times,
                    "open": base_open,
                    "high": base_high,
                    "low": base_low,
                    "close": base_close,
                    "volume": 1.0,
                }
            )
            df_1h.to_csv(sym_dir / "1h.csv", index=False)

            n_sub = n_base * 12
            sub_times = pd.date_range(start=start, periods=n_sub, freq="5min")
            sub_close = np.linspace(100.0, 140.0, num=n_sub)
            sub_open = np.roll(sub_close, 1)
            sub_open[0] = sub_close[0]
            sub_high = np.maximum(sub_open, sub_close) + 0.2
            sub_low = np.minimum(sub_open, sub_close) - 0.2
            df_5m = pd.DataFrame(
                {
                    "datetime": sub_times,
                    "open": sub_open,
                    "high": sub_high,
                    "low": sub_low,
                    "close": sub_close,
                    "volume": 1.0,
                }
            )
            df_5m.to_csv(sym_dir / "5m.csv", index=False)

            cfg = NairaConfig(
                entry_mode="none",
                confirm_higher_tfs=False,
                timing_timeframe="",
                alignment_threshold=0.0,
                slope_threshold_pct=0.0,
                adx_threshold=0.0,
                min_confidence=0.0,
            )
            e = NairaEngine(data_dir=base_dir, config=cfg)
            r = e.backtest(
                symbol="TEST",
                provider="csv",
                base_timeframe="1h",
                starting_cash=10000.0,
                bar_magnifier=True,
                magnifier_timeframe="5m",
            )
            self.assertIn("metrics", r)
            self.assertIn("trades", r)

    def test_backtest_confluence_gate_blocks_entries(self):
        import pandas as pd
        import numpy as np

        with tempfile.TemporaryDirectory() as td:
            base_dir = td
            sym_dir = Path(base_dir) / "history" / "csv" / "GATE"
            os.makedirs(sym_dir, exist_ok=True)

            start = pd.Timestamp("2025-01-01T00:00:00Z")
            n = 120
            times = pd.date_range(start=start, periods=n, freq="1h")
            close = np.concatenate([np.linspace(100.0, 110.0, 60), np.linspace(200.0, 210.0, 60)])
            open_ = np.roll(close, 1)
            open_[0] = close[0]
            high = np.maximum(open_, close) + 0.2
            low = np.minimum(open_, close) - 0.2
            df_1h = pd.DataFrame({"datetime": times, "open": open_, "high": high, "low": low, "close": close, "volume": 1.0})
            df_1h.to_csv(sym_dir / "1h.csv", index=False)

            cfg = NairaConfig(
                strategy_mode="multi",
                entry_mode="hybrid",
                confirm_higher_tfs=False,
                timing_timeframe="",
                alignment_threshold=0.0,
                slope_threshold_pct=0.0,
                adx_threshold=0.0,
                min_confidence=0.0,
            )
            e = NairaEngine(data_dir=base_dir, config=cfg)
            r = e.backtest(symbol="GATE", provider="csv", base_timeframe="1h", max_bars=120)
            self.assertIn("trades", r)
            self.assertEqual(len(r.get("trades") or []), 0)

    def test_history_file_exists(self):
        p = Path(settings.DATA_DIR) / "history" / "csv" / "TEST" / "1h.csv"
        self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
