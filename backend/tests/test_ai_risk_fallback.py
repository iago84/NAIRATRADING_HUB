import sys
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.naira_engine import NairaEngine, NairaConfig


def test_ai_risk_falls_back_to_fixed_risk_when_no_model():
    with tempfile.TemporaryDirectory() as td:
        sym_dir = Path(td) / "history" / "csv" / "TEST"
        sym_dir.mkdir(parents=True, exist_ok=True)

        start = pd.Timestamp("2025-01-01T00:00:00Z")
        n = 500
        times = pd.date_range(start=start, periods=n, freq="1h")
        close = np.linspace(100.0, 140.0, num=n)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        high = np.maximum(open_, close) + 0.5
        low = np.minimum(open_, close) - 0.5
        df = pd.DataFrame(
            {
                "datetime": times,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
            }
        )
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
        )
        eng = NairaEngine(data_dir=str(td), config=cfg)
        r = eng.backtest(
            symbol="TEST",
            provider="csv",
            base_timeframe="1h",
            max_bars=500,
            sizing_mode="ai_risk",
            risk_per_trade_pct=2.0,
            ai_assisted_sizing=True,
            ai_risk_min_pct=1.0,
            ai_risk_max_pct=5.0,
            max_leverage=1.0,
            apply_execution_gates=False,
        )
        trades = r.get("trades") or []
        assert len(trades) > 0
        meta = (trades[0].get("entry_meta") or {})
        assert meta.get("sizing_mode_used") in ("fixed_risk_fallback", "fixed_risk")
        assert float(meta.get("risk_pct_used") or 0.0) == 2.0
