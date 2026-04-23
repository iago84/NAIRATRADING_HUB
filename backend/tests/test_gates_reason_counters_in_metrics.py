from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_metrics_contains_gate_reason_counts():
    cfg = NairaConfig(strategy_mode="multi", entry_mode="hybrid")
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
    r = eng.backtest(symbol="LTCUSDT", provider="csv", base_timeframe="1h", max_bars=300)
    m = r.get("metrics") or {}
    assert "gate_reason_counts" in m
    assert isinstance(m["gate_reason_counts"], dict)
