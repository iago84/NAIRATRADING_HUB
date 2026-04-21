from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

Regime = Literal["trend", "range", "transition"]
BrainId = Literal["trend", "pullback", "breakout", "mean_reversion"]


@dataclass(frozen=True)
class ActiveBrains:
    dominant: BrainId
    secondary: BrainId | None = None


def _frame_by_tf(frames: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in frames or []:
        tf = str(f.get("timeframe") or "")
        if tf:
            out[tf] = dict(f)
    return out


def classify_regime(frames: List[Dict[str, Any]]) -> Regime:
    by_tf = _frame_by_tf(frames)
    f = by_tf.get("4h") or by_tf.get("1d") or {}
    adx = float(f.get("adx") or 0.0)
    comp = float(f.get("ema_compression") or 0.0)
    slope = float(f.get("slope_score") or 0.0)
    trending = (adx >= 18.0) and (abs(slope) >= 0.05) and (comp <= 3.0)
    ranging = (adx <= 14.0) and (comp >= 3.5)
    if trending:
        return "trend"
    if ranging:
        return "range"
    return "transition"


def pick_brains(regime: Regime) -> ActiveBrains:
    if regime == "trend":
        return ActiveBrains(dominant="trend", secondary="pullback")
    if regime == "range":
        return ActiveBrains(dominant="mean_reversion", secondary=None)
    return ActiveBrains(dominant="breakout", secondary="trend")
