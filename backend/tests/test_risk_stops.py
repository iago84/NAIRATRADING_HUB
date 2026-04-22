from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.risk_stops import RiskStopConfig, apply_risk_stop


def test_stop_immediate_on_max_drawdown():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_immediate",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=49.0, equity=49.0, has_open_position=False)
    assert res.triggered is True
    assert res.reason == "max_drawdown"
    assert res.should_terminate is True


def test_stop_after_close_waits_if_open_position():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_after_close",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=49.0, equity=49.0, has_open_position=True)
    assert res.triggered is True
    assert res.reason == "max_drawdown"
    assert res.should_terminate is False
    assert res.block_new_trades is True


def test_no_stop_when_healthy():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_immediate",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=100.0, equity=100.0, has_open_position=False)
    assert res.triggered is False
