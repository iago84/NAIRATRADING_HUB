import sys
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.naira_engine import NairaEngine, NairaConfig


def test_portfolio_backtest_drawdown_is_positive_pct_and_has_equity_curve():
    with tempfile.TemporaryDirectory() as td:
        for sym in ("A", "B"):
            sym_dir = Path(td) / "history" / "csv" / sym
            sym_dir.mkdir(parents=True, exist_ok=True)
            start = pd.Timestamp("2025-01-01T00:00:00Z")
            n = 300
            times = pd.date_range(start=start, periods=n, freq="1h")
            close = np.linspace(100.0, 120.0, num=n)
            if sym == "B":
                close[200:] = np.linspace(120.0, 105.0, num=n - 200)
            open_ = np.roll(close, 1)
            open_[0] = close[0]
            high = np.maximum(open_, close) + 0.5
            low = np.minimum(open_, close) - 0.5
            df = pd.DataFrame({"datetime": times, "open": open_, "high": high, "low": low, "close": close, "volume": 1000.0})
            df.to_csv(sym_dir / "1h.csv", index=False)

        cfg = NairaConfig(
            strategy_mode="multi",
            entry_mode="none",
            confirm_higher_tfs=False,
            timing_timeframe="",
            alignment_threshold=0.0,
            slope_threshold_pct=0.0,
            adx_threshold=0.0,
            min_confidence=0.0,
            sl_atr_mult=1.0,
            tp_atr_mult=3.0,
        )
        e = NairaEngine(data_dir=str(td), config=cfg)
        r = e.portfolio_backtest(symbols=["A", "B"], provider="csv", base_timeframe="1h", max_bars=300, max_positions=1)
        met = r.get("metrics") or {}
        assert float(met.get("max_drawdown_pct") or 0.0) >= 0.0
        eq = r.get("equity_curve") or []
        assert len(eq) > 10
