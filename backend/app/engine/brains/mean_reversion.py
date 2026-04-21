from __future__ import annotations

from ..entry_rules import decide_entry
from .types import BrainContext, BrainSignal


def run(ctx: BrainContext) -> BrainSignal:
    a = ctx.analysis
    direction = str(a.get("direction") or "neutral")
    confidence = float(a.get("confidence") or 0.0)
    score = float(a.get("opportunity_score") or 0.0)
    reasons = ["brain=mean_reversion"]
    if direction not in ("buy", "sell"):
        return BrainSignal(
            brain="mean_reversion",
            direction="neutral",
            confidence=0.0,
            opportunity_score=0.0,
            reasons=reasons + ["direction=neutral"],
            risk=dict(a.get("risk") or {}),
            ai_p_win=None,
        )
    dec = decide_entry(df=ctx.df_feat_base, side=direction, mode="mean_reversion", tol_atr=0.6)
    if not dec.ok:
        return BrainSignal(
            brain="mean_reversion",
            direction="neutral",
            confidence=float(confidence) * 0.35,
            opportunity_score=float(score) * 0.35,
            reasons=reasons + ["setup_not_ok"],
            risk=dict(a.get("risk") or {}),
            ai_p_win=None,
        )
    return BrainSignal(
        brain="mean_reversion",
        direction=direction,  # type: ignore[arg-type]
        confidence=float(confidence),
        opportunity_score=float(score),
        reasons=reasons + ["setup_ok"],
        risk=dict(a.get("risk") or {}),
        ai_p_win=None,
    )
