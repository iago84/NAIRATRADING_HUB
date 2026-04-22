import sys
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.naira_engine import NairaEngine, NairaConfig


def test_trade_pnl_total_includes_partials():
    with tempfile.TemporaryDirectory() as td:
        sym_dir = Path(td) / "history" / "csv" / "TEST"
        sym_dir.mkdir(parents=True, exist_ok=True)

        start = pd.Timestamp("2025-01-01T00:00:00Z")
        n = 600
        times = pd.date_range(start=start, periods=n, freq="1h")
        close = np.linspace(100.0, 140.0, num=n)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        high = np.maximum(open_, close) + 1.0
        low = np.minimum(open_, close) - 1.0
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
            tp_atr_mult=4.0,
            partial_1r_pct=0.5,
            partial_2r_pct=0.25,
        )
        eng = NairaEngine(data_dir=str(td), config=cfg)
        r = eng.backtest(symbol="TEST", provider="csv", base_timeframe="1h", max_bars=600, apply_execution_gates=False, include_debug=True)
        trades = r.get("trades") or []
        assert len(trades) > 0
        t0 = trades[0]
        partials = t0.get("partials") or []
        pnl_total = float(t0.get("pnl_total") or 0.0)
        pnl_final = float(t0.get("pnl_final") or 0.0)
        partial_sum = sum(float(x.get("pnl") or 0.0) for x in partials)
        assert abs(pnl_total - (pnl_final + partial_sum)) < 1e-9
