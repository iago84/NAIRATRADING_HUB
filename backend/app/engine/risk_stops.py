from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


RiskStopPolicy = Literal["stop_immediate", "stop_no_new_trades", "stop_after_close"]


@dataclass(frozen=True)
class RiskStopConfig:
    max_equity_drawdown_pct: float = 50.0
    free_cash_min_pct: float = 0.20
    policy: RiskStopPolicy = "stop_immediate"


@dataclass(frozen=True)
class RiskStopResult:
    triggered: bool
    reason: str
    policy: str
    block_new_trades: bool
    should_terminate: bool
    threshold_equity: Optional[float]
    threshold_free_cash: Optional[float]


def apply_risk_stop(*, cfg: RiskStopConfig, starting_cash: float, cash: float, equity: float, has_open_position: bool) -> RiskStopResult:
    start = float(starting_cash)
    eq = float(equity)
    free_cash = float(cash)
    max_dd = float(cfg.max_equity_drawdown_pct)
    free_min = float(cfg.free_cash_min_pct)
    policy = str(cfg.policy)

    threshold_equity = start * (1.0 - max_dd / 100.0)
    threshold_free_cash = start * free_min

    reason = ""
    triggered = False
    if max_dd > 0 and eq <= threshold_equity:
        triggered = True
        reason = "max_drawdown"
    elif free_min > 0 and free_cash < threshold_free_cash:
        triggered = True
        reason = "free_cash_min"

    if not triggered:
        return RiskStopResult(
            triggered=False,
            reason="",
            policy=policy,
            block_new_trades=False,
            should_terminate=False,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_immediate":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=True,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_no_new_trades":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=False,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_after_close":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=(not bool(has_open_position)),
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    return RiskStopResult(
        triggered=True,
        reason=reason,
        policy=policy,
        block_new_trades=True,
        should_terminate=True,
        threshold_equity=float(threshold_equity),
        threshold_free_cash=float(threshold_free_cash),
    )
