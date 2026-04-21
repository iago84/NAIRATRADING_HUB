from __future__ import annotations

from .types import BrainContext, BrainSignal


def run(ctx: BrainContext) -> BrainSignal:
    a = ctx.analysis
    direction = str(a.get("direction") or "neutral")
    confidence = float(a.get("confidence") or 0.0)
    score = float(a.get("opportunity_score") or 0.0)
    reasons = [f"brain=trend"]
    reasons.extend(list(a.get("reasons") or [])[:6])
    return BrainSignal(
        brain="trend",
        direction=direction,  # type: ignore[arg-type]
        confidence=confidence,
        opportunity_score=score,
        reasons=reasons,
        risk=dict(a.get("risk") or {}),
        ai_p_win=None,
    )
