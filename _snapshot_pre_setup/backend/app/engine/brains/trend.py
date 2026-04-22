from __future__ import annotations

from .types import BrainContext, BrainSignal


def run(ctx: BrainContext) -> BrainSignal:
    a = ctx.analysis
    direction = str(a.get("direction") or "neutral")
    confidence = float(a.get("confidence") or 0.0)
    score = float(a.get("opportunity_score") or 0.0)
    reasons = [f"brain=trend"]
    by_tf = {str(f.get("timeframe") or ""): f for f in (ctx.frames or [])}
    f1d = by_tf.get("1d") or {}
    f1w = by_tf.get("1w") or {}
    d1d = str(f1d.get("direction") or "neutral")
    d1w = str(f1w.get("direction") or "neutral")
    a1d = float(f1d.get("alignment") or 0.0)
    a1w = float(f1w.get("alignment") or 0.0)
    req_ok = True
    if direction in ("buy", "sell"):
        if d1d != direction:
            req_ok = False
        if "1w" in by_tf and d1w != direction:
            req_ok = False
        if a1d < 0.7:
            req_ok = False
        if "1w" in by_tf and a1w < 0.7:
            req_ok = False
    else:
        req_ok = False
    if not req_ok:
        return BrainSignal(
            brain="trend",
            direction="neutral",
            confidence=float(confidence) * 0.2,
            opportunity_score=0.0,
            reasons=reasons + ["trend_requirements_failed"],
            risk=dict(a.get("risk") or {}),
            ai_p_win=None,
        )
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
