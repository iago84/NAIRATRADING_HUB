from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .entry_rules import break_retest_entry, mean_reversion_entry, pullback_entry
from .levels import latest_fractal_levels


def _wick_reject_ratio(last: pd.Series) -> float:
    try:
        o = float(last.get("open"))
        h = float(last.get("high"))
        l = float(last.get("low"))
        c = float(last.get("close"))
        body = abs(float(c) - float(o))
        uw = float(h) - max(float(o), float(c))
        lw = min(float(o), float(c)) - float(l)
        return float(max(uw, lw) / max(1e-9, body))
    except Exception:
        return 0.0


def _fractal_distance_atr(df: pd.DataFrame) -> float:
    try:
        if df is None or df.empty or len(df) < 10:
            return 0.0
        last = df.iloc[-1]
        atr = float(last.get("atr") or 0.0)
        if atr <= 0:
            return 0.0
        fr = latest_fractal_levels(df, lookback=2)
        c = float(last.get("close") or 0.0)
        d: List[float] = []
        if fr.get("fractal_high") is not None:
            d.append(abs(float(c) - float(fr["fractal_high"])))
        if fr.get("fractal_low") is not None:
            d.append(abs(float(c) - float(fr["fractal_low"])))
        if not d:
            return 0.0
        return float(min(d) / atr)
    except Exception:
        return 0.0


def _get_frame(frames: List[Dict[str, Any]], base_timeframe: str) -> Dict[str, Any]:
    by_tf = {str(f.get("timeframe") or ""): f for f in (frames or [])}
    return dict(by_tf.get(str(base_timeframe)) or (frames[-1] if frames else {}))


def _clip01(x: float) -> float:
    return float(np.clip(float(x), 0.0, 1.0))


def classify_setups(df_feat_base: pd.DataFrame, frames: List[Dict[str, Any]], base_timeframe: str, top_n: int = 3) -> Dict[str, Any]:
    df = df_feat_base
    if df is None or df.empty:
        return {"setup_primary": "unknown", "setup_candidates": []}
    last = df.iloc[-1]
    f = _get_frame(frames, base_timeframe=base_timeframe)

    trend_age = float(last.get("trend_age_bars") or f.get("trend_age_bars") or 0.0)
    comp = float(last.get("ema_compression") or f.get("ema_compression") or 0.0)
    adx = float(last.get("adx") or 0.0)
    ali = float(last.get("alignment") or 0.0)
    r2 = float(last.get("regression_r2") or 0.0)
    slope = float(last.get("slope_score") or 0.0)
    curv = float(last.get("curvature") or 0.0)
    lvl = float(f.get("level_confluence_score") or 0.0)
    wick = _wick_reject_ratio(last)
    frd = _fractal_distance_atr(df)

    side = "buy"
    try:
        d = str(f.get("direction") or last.get("direction") or "neutral")
        if d == "sell":
            side = "sell"
    except Exception:
        pass

    pull = pullback_entry(df, side=side, tol_atr=0.6)
    br = break_retest_entry(df, side=side, tol_atr=0.6)
    mr = mean_reversion_entry(df, side=side, dist_atr=1.0, min_reject_wick_ratio=1.0)

    cand: List[Dict[str, Any]] = []

    breakout_score = _clip01(
        0.30 * (adx / 50.0)
        + 0.25 * ali
        + 0.20 * r2
        + 0.15 * _clip01(abs(slope) / 2.0)
        + 0.10 * _clip01(max(0.0, 2.0 - comp) / 2.0)
    )
    breakout_score *= _clip01(max(0.0, 3.0 - trend_age) / 3.0)
    cand.append(
        {
            "type": "breakout",
            "score": float(breakout_score),
            "reasons": ["momentum"],
            "features": {"adx": adx, "alignment": ali, "r2": r2, "ema_compression": comp, "trend_age_bars": trend_age},
        }
    )

    br_score = 1.0 if br.ok else _clip01(max(0.0, 2.0 - frd) / 2.0)
    cand.append(
        {
            "type": "break_retest",
            "score": float(br_score),
            "reasons": ["break_retest" if br.ok else "near_fractal"],
            "features": {"fractal_distance_atr": frd},
        }
    )

    pb_ema_score = 1.0 if pull.ok else 0.0
    cand.append(
        {
            "type": "pullback_ema",
            "score": float(pb_ema_score),
            "reasons": ["ema_pullback" if pull.ok else "no_pullback"],
            "features": {},
        }
    )

    pb_lvl_score = _clip01(lvl)
    cand.append(
        {
            "type": "pullback_level",
            "score": float(pb_lvl_score),
            "reasons": ["level_confluence"],
            "features": {"level_confluence_score": lvl},
        }
    )

    mr_score = 1.0 if mr.ok else 0.0
    mr_score *= _clip01(max(0.0, 3.0 - (adx / 10.0)) / 3.0)
    mr_score *= _clip01(min(2.5, wick) / 2.5)
    cand.append(
        {
            "type": "mean_reversion",
            "score": float(mr_score),
            "reasons": ["mr_reject" if mr.ok else "no_reject"],
            "features": {"wick_reject_ratio": wick},
        }
    )

    ex_score = (
        _clip01(max(0.0, trend_age - 6.0) / 6.0)
        * _clip01(max(0.0, comp - 3.0) / 3.0)
        * _clip01(min(2.5, wick) / 2.5)
        * _clip01(min(1.0, abs(curv) * 50.0))
    )
    cand.append(
        {
            "type": "exhaustion",
            "score": float(ex_score),
            "reasons": ["late+compressed"],
            "features": {"trend_age_bars": trend_age, "ema_compression": comp, "wick_reject_ratio": wick, "curvature": curv},
        }
    )

    cand.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    top = cand[: max(1, int(top_n))]
    primary = str(top[0].get("type") or "unknown") if top else "unknown"
    return {"setup_primary": primary, "setup_candidates": top, "setup_features": {"wick_reject_ratio": wick, "fractal_distance_atr": frd}}
