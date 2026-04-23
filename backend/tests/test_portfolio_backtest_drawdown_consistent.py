from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_portfolio_backtest_drawdown_is_non_negative():
    cfg = NairaConfig(strategy_mode="multi", entry_mode="hybrid")
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
    r = eng.portfolio_backtest(provider="csv", symbols=["LTCUSDT"], base_timeframe="1h", max_bars=300)
    m = r.get("metrics") or {}
    dd = float(m.get("max_drawdown_pct") or 0.0)
    assert dd >= 0.0
