from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_trade_contains_exit_meta_lock_fields():
    cfg = NairaConfig(strategy_mode="multi", entry_mode="hybrid", lock_trigger_r=0.0, lock_r=0.0)
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
    r = eng.backtest(symbol="LTCUSDT", provider="csv", base_timeframe="1h", max_bars=500)
    trades = r.get("trades") or []
    assert trades
    em = trades[0].get("exit_meta") or {}
    assert "lock_triggered" in em
