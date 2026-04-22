from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .ai_gate import allow as ai_allow
from .brains import run_breakout, run_mean_reversion, run_pullback, run_trend
from .brains.types import BrainContext, BrainSignal
from .dataset import FEATURES
from .ensemble import combine
from .execution_gates import confluence_gate, execution_threshold_gate, structural_gate
from .naira_engine import NairaEngine
from .regime_router import Regime, classify_regime, pick_brains


@dataclass(frozen=True)
class MultiBrainResult:
    regime: Regime
    dominant: BrainSignal
    secondary: Optional[BrainSignal]
    final: BrainSignal
    gate: Dict[str, Any]


def _run_brain(brain_id: str, ctx: BrainContext) -> BrainSignal:
    if brain_id == "trend":
        return run_trend(ctx)
    if brain_id == "pullback":
        return run_pullback(ctx)
    if brain_id == "breakout":
        return run_breakout(ctx)
    return run_mean_reversion(ctx)


def _combine(dominant: BrainSignal, secondary: Optional[BrainSignal]) -> BrainSignal:
    return combine(dominant, secondary)


def _build_ai_features(df_feat_base: pd.DataFrame, frames: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {k: 0.0 for k in FEATURES}
    by_tf = {str(f.get("timeframe") or ""): f for f in (frames or [])}
    f = by_tf.get("1h") or by_tf.get("4h") or (frames[-1] if frames else {})
    for k in ("alignment", "slope_score", "regression_slope_pct", "regression_r2", "adx", "atr", "atr_pct", "ema_compression"):
        try:
            out[k] = float(f.get(k) or 0.0)
        except Exception:
            out[k] = 0.0
    try:
        last = df_feat_base.iloc[-1]
        close = float(last.get("close") or 0.0)
        atr = float(last.get("atr") or 0.0)
        if close > 0 and atr > 0:
            out["dist_ema25_atr"] = abs(close - float(last.get("ema_25") or close)) / atr if "ema_25" in df_feat_base.columns else 0.0
            out["dist_ema80_atr"] = abs(close - float(last.get("ema_80") or close)) / atr if "ema_80" in df_feat_base.columns else 0.0
            out["dist_ema220_atr"] = abs(close - float(last.get("ema_220") or close)) / atr if "ema_220" in df_feat_base.columns else 0.0
    except Exception:
        pass
    return out


def run_multi_brain(
    engine: NairaEngine,
    symbol: str,
    provider: str,
    base_timeframe: str,
    tranche: str,
    csv_path: Optional[str] = None,
    timeframes: Optional[List[str]] = None,
    include_debug: bool = False,
) -> Tuple[Dict[str, Any], MultiBrainResult]:
    analysis = engine.analyze(
        symbol=symbol,
        provider=provider,
        base_timeframe=base_timeframe,
        csv_path=csv_path,
        timeframes=timeframes,
        include_debug=bool(include_debug),
    )
    df_base = engine.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider, csv_path=csv_path)
    df_feat = engine._apply_features(df_base)
    frames = list(analysis.get("frames") or [])
    regime = classify_regime(frames)
    g1 = structural_gate(frames)
    g2 = confluence_gate(frames, base_timeframe=str(base_timeframe))
    g3 = execution_threshold_gate(frames, base_timeframe=str(base_timeframe))
    if not (g1.ok and g2.ok and g3.ok):
        merged = dict(analysis)
        merged["direction"] = "neutral"
        merged["confidence"] = float(analysis.get("confidence") or 0.0) * 0.2
        merged["opportunity_score"] = 0.0
        merged["reasons"] = list(analysis.get("reasons") or []) + list(g1.reasons) + list(g2.reasons) + list(g3.reasons) + [f"regime={regime}"]
        if include_debug:
            merged["debug"] = {"regime": regime, "gates": {"structural": g1.debug, "confluence": g2.debug, "execution": g3.debug}}
        neutral = BrainSignal(brain="trend", direction="neutral", confidence=float(merged["confidence"]), opportunity_score=0.0, reasons=list(merged["reasons"]), risk=dict(analysis.get("risk") or {}), ai_p_win=None)
        return merged, MultiBrainResult(regime=regime, dominant=neutral, secondary=None, final=neutral, gate={"ok": False, "reason": "execution_gates"})
    active = pick_brains(regime)
    ctx = BrainContext(
        symbol=str(symbol),
        provider=str(provider),
        base_timeframe=str(base_timeframe),
        csv_path=str(csv_path) if csv_path else None,
        analysis=dict(analysis),
        frames=frames,
        df_feat_base=df_feat,
    )
    dom = _run_brain(active.dominant, ctx)
    sec = _run_brain(active.secondary, ctx) if active.secondary else None
    ai_feats = _build_ai_features(df_feat, frames)
    p_win = engine.score_ai(ai_feats)
    dom2 = BrainSignal(**{**dom.__dict__, "ai_p_win": p_win})
    sec2 = BrainSignal(**{**sec.__dict__, "ai_p_win": p_win}) if sec is not None else None
    combined = _combine(dom2, sec2)
    gate = ai_allow(p_win, tranche)  # type: ignore[arg-type]
    if not gate.ok:
        combined = BrainSignal(
            brain=combined.brain,
            direction="neutral",
            confidence=float(combined.confidence) * 0.2,
            opportunity_score=float(combined.opportunity_score) * 0.2,
            reasons=list(combined.reasons) + [f"ai_gate={gate.reason}"],
            risk=dict(combined.risk),
            ai_p_win=p_win,
        )
    merged = dict(analysis)
    merged["direction"] = combined.direction
    merged["confidence"] = float(combined.confidence)
    merged["opportunity_score"] = float(combined.opportunity_score)
    merged["reasons"] = list(analysis.get("reasons") or []) + [f"regime={regime}", f"brain={combined.brain}"]
    if include_debug:
        dbg = {
            "regime": regime,
            "dominant": dom2.brain,
            "secondary": sec2.brain if sec2 else None,
            "ai_p_win": p_win,
            "ai_gate": gate.__dict__,
        }
        dbg["gates"] = {"structural": g1.debug, "confluence": g2.debug, "execution": g3.debug}
        merged["debug"] = dbg
    return merged, MultiBrainResult(regime=regime, dominant=dom2, secondary=sec2, final=combined, gate=gate.__dict__)
