from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_entry_meta_contains_sizing_audit_fields():
    orig = {
        "CONFLUENCE_MIN": settings.CONFLUENCE_MIN,
        "STRUCT_ALIGN_4H_MIN": settings.STRUCT_ALIGN_4H_MIN,
        "STRUCT_ALIGN_1D_MIN": settings.STRUCT_ALIGN_1D_MIN,
        "EXEC_CONF_MIN": settings.EXEC_CONF_MIN,
        "EXEC_ALIGN_MIN": settings.EXEC_ALIGN_MIN,
    }
    try:
        object.__setattr__(settings, "CONFLUENCE_MIN", 0.0)
        object.__setattr__(settings, "STRUCT_ALIGN_4H_MIN", 0.0)
        object.__setattr__(settings, "STRUCT_ALIGN_1D_MIN", 0.0)
        object.__setattr__(settings, "EXEC_CONF_MIN", 0.0)
        object.__setattr__(settings, "EXEC_ALIGN_MIN", 0.0)

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
        eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
        r = eng.backtest(
            symbol="LTCUSDT",
            provider="csv",
            base_timeframe="1h",
            max_bars=500,
            sizing_mode="fixed_risk",
            risk_per_trade_pct=2.0,
            max_leverage=1.0,
            ai_assisted_sizing=False,
        )
        trades = r.get("trades") or []
        assert trades, "expected at least one trade in csv fixture"
        em = (trades[0].get("entry_meta") or {})
        assert "risk_pct_used" in em
        assert "sizing_mode_used" in em
    finally:
        for k, v in orig.items():
            object.__setattr__(settings, k, v)
