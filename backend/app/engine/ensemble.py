from __future__ import annotations

from typing import Optional

from .brains.types import BrainSignal


def combine(dominant: BrainSignal, secondary: Optional[BrainSignal]) -> BrainSignal:
    conf = float(dominant.confidence)
    score = float(dominant.opportunity_score)
    reasons = list(dominant.reasons)
    if secondary is not None:
        if secondary.direction == dominant.direction and secondary.direction != "neutral":
            conf = min(1.0, conf + 0.08)
            score = min(100.0, score + 6.0)
            reasons.append("ensemble=agree")
        elif secondary.direction != "neutral" and dominant.direction != "neutral" and secondary.direction != dominant.direction:
            conf = max(0.0, conf - 0.12)
            score = max(0.0, score - 10.0)
            reasons.append("ensemble=disagree")
    return BrainSignal(
        brain=dominant.brain,
        direction=dominant.direction,
        confidence=float(conf),
        opportunity_score=float(score),
        reasons=reasons,
        risk=dict(dominant.risk),
        ai_p_win=dominant.ai_p_win,
    )
