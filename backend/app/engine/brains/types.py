from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

Direction = Literal["buy", "sell", "neutral"]
BrainId = Literal["trend", "pullback", "breakout", "mean_reversion"]


@dataclass(frozen=True)
class BrainContext:
    symbol: str
    provider: str
    base_timeframe: str
    csv_path: str | None
    analysis: Dict[str, Any]
    frames: List[Dict[str, Any]]
    df_feat_base: Any


@dataclass(frozen=True)
class BrainSignal:
    brain: BrainId
    direction: Direction
    confidence: float
    opportunity_score: float
    reasons: List[str]
    risk: Dict[str, Any]
    ai_p_win: float | None = None
