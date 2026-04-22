from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..core.config import settings

Tranche = Literal["T0", "T1", "T2", "T3"]


@dataclass(frozen=True)
class GateDecision:
    ok: bool
    threshold: float
    p_win: float
    reason: str


def threshold_for_tranche(tranche: Tranche) -> float:
    if tranche == "T0":
        return float(settings.AI_GATE_T0)
    if tranche == "T1":
        return float(settings.AI_GATE_T1)
    if tranche == "T2":
        return float(settings.AI_GATE_T2)
    return float(settings.AI_GATE_T3)


def allow(p_win: float | None, tranche: Tranche) -> GateDecision:
    thr = float(threshold_for_tranche(tranche))
    if p_win is None:
        return GateDecision(ok=True, threshold=thr, p_win=0.0, reason="no_model")
    p = float(p_win)
    if p >= thr:
        return GateDecision(ok=True, threshold=thr, p_win=p, reason="ok")
    return GateDecision(ok=False, threshold=thr, p_win=p, reason="below_threshold")
