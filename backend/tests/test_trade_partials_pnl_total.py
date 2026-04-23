from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_trade_contains_pnl_partials_and_pnl_total():
    cfg = NairaConfig(strategy_mode="multi", entry_mode="hybrid")
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
    r = eng.backtest(symbol="LTCUSDT", provider="csv", base_timeframe="1h", max_bars=800)
    trades = r.get("trades") or []
    assert trades
    t = trades[0]
    assert "pnl_partials" in t
    assert "pnl_total" in t
    assert isinstance(t["pnl_partials"], list)
    assert abs(float(t["pnl_total"]) - (float(t["pnl"]) + sum(float(x) for x in t["pnl_partials"]))) < 1e-9
