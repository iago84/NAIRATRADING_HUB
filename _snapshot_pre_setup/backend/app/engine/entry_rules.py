from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Literal

import numpy as np
import pandas as pd

from .ohlc import normalize_ohlcv
from .levels import latest_fractal_levels


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class EntryDecision:
    ok: bool
    kind: str
    details: Dict[str, float]


def normalize_ohlcv_keep(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    base = normalize_ohlcv(df)
    if base.empty:
        return base
    try:
        extras = df.copy()
        cols_lower = {c.lower(): c for c in extras.columns}
        if "datetime" not in extras.columns:
            if "datetime" in cols_lower:
                extras.rename(columns={cols_lower["datetime"]: "datetime"}, inplace=True)
            elif "time" in cols_lower:
                extras.rename(columns={cols_lower["time"]: "datetime"}, inplace=True)
            elif "timestamp" in cols_lower:
                extras.rename(columns={cols_lower["timestamp"]: "datetime"}, inplace=True)
        if "datetime" not in extras.columns:
            return base
        extras["datetime"] = pd.to_datetime(extras["datetime"], errors="coerce")
        extras = extras.dropna(subset=["datetime"]).drop_duplicates(subset=["datetime"]).set_index("datetime")
        out = base.set_index("datetime")
        for c in extras.columns:
            if c not in out.columns:
                out[c] = extras[c]
        return out.reset_index()
    except Exception:
        return base


def _near(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= float(tol)


def pullback_entry(
    df: pd.DataFrame,
    side: Side,
    atr_col: str = "atr",
    ema_fast: str = "ema_25",
    ema_slow: str = "ema_80",
    tol_atr: float = 0.6,
) -> EntryDecision:
    df = normalize_ohlcv_keep(df)
    if df is None or df.empty or len(df) < 5:
        return EntryDecision(ok=False, kind="pullback", details={})
    last = df.iloc[-1]
    atr = float(last.get(atr_col)) if atr_col in df.columns and pd.notna(last.get(atr_col)) else None
    if atr is None or atr <= 0:
        return EntryDecision(ok=False, kind="pullback", details={})
    if ema_fast not in df.columns or ema_slow not in df.columns:
        return EntryDecision(ok=False, kind="pullback", details={})
    c = float(last["close"])
    h = float(last["high"])
    l = float(last["low"])
    e25 = float(last.get(ema_fast))
    e80 = float(last.get(ema_slow))
    tol = float(tol_atr) * float(atr)
    if side == "buy":
        touched = _near(l, e25, tol) or _near(l, e80, tol) or (l <= e25 <= h) or (l <= e80 <= h)
        recovered = c >= e25
        return EntryDecision(ok=bool(touched and recovered), kind="pullback", details={"atr": atr, "tol": tol, "ema_fast": e25, "ema_slow": e80, "close": c})
    touched = _near(h, e25, tol) or _near(h, e80, tol) or (l <= e25 <= h) or (l <= e80 <= h)
    recovered = c <= e25
    return EntryDecision(ok=bool(touched and recovered), kind="pullback", details={"atr": atr, "tol": tol, "ema_fast": e25, "ema_slow": e80, "close": c})


def break_retest_entry(
    df: pd.DataFrame,
    side: Side,
    atr_col: str = "atr",
    tol_atr: float = 0.6,
) -> EntryDecision:
    df = normalize_ohlcv_keep(df)
    if df is None or df.empty or len(df) < 10:
        return EntryDecision(ok=False, kind="break_retest", details={})
    last = df.iloc[-1]
    atr = float(last.get(atr_col)) if atr_col in df.columns and pd.notna(last.get(atr_col)) else None
    if atr is None or atr <= 0:
        return EntryDecision(ok=False, kind="break_retest", details={})
    fr = latest_fractal_levels(df, lookback=2)
    tol = float(tol_atr) * float(atr)
    c = float(last["close"])
    h = float(last["high"])
    l = float(last["low"])
    if side == "buy":
        lvl = fr.get("fractal_high")
        if lvl is None:
            return EntryDecision(ok=False, kind="break_retest", details={})
        broke = c >= float(lvl)
        retest = (l <= float(lvl) <= h) or _near(l, float(lvl), tol)
        ok = bool(broke and retest and c >= float(lvl))
        return EntryDecision(ok=ok, kind="break_retest", details={"atr": atr, "tol": tol, "level": float(lvl), "close": c})
    lvl = fr.get("fractal_low")
    if lvl is None:
        return EntryDecision(ok=False, kind="break_retest", details={})
    broke = c <= float(lvl)
    retest = (l <= float(lvl) <= h) or _near(h, float(lvl), tol)
    ok = bool(broke and retest and c <= float(lvl))
    return EntryDecision(ok=ok, kind="break_retest", details={"atr": atr, "tol": tol, "level": float(lvl), "close": c})


def mean_reversion_entry(
    df: pd.DataFrame,
    side: Side,
    atr_col: str = "atr",
    ema_mid: str = "ema_25",
    dist_atr: float = 1.0,
    min_reject_wick_ratio: float = 1.0,
) -> EntryDecision:
    df = normalize_ohlcv_keep(df)
    if df is None or df.empty or len(df) < 5:
        return EntryDecision(ok=False, kind="mean_reversion", details={})
    last = df.iloc[-1]
    atr = float(last.get(atr_col)) if atr_col in df.columns and pd.notna(last.get(atr_col)) else None
    if atr is None or atr <= 0:
        return EntryDecision(ok=False, kind="mean_reversion", details={})
    if ema_mid not in df.columns:
        return EntryDecision(ok=False, kind="mean_reversion", details={})
    e = float(last.get(ema_mid))
    o = float(last["open"])
    h = float(last["high"])
    l = float(last["low"])
    c = float(last["close"])
    body = abs(float(c) - float(o))
    uw = float(h) - max(float(o), float(c))
    lw = min(float(o), float(c)) - float(l)
    w = float(min_reject_wick_ratio)
    d = float(dist_atr) * float(atr)
    if side == "buy":
        away = float(c) <= float(e) - float(d)
        rej = (float(c) > float(o)) and (float(lw) >= float(w) * max(1e-9, float(body)))
        return EntryDecision(ok=bool(away and rej), kind="mean_reversion", details={"atr": atr, "ema_mid": e, "dist_atr": float(dist_atr), "close": c})
    away = float(c) >= float(e) + float(d)
    rej = (float(c) < float(o)) and (float(uw) >= float(w) * max(1e-9, float(body)))
    return EntryDecision(ok=bool(away and rej), kind="mean_reversion", details={"atr": atr, "ema_mid": e, "dist_atr": float(dist_atr), "close": c})


def decide_entry(
    df: pd.DataFrame,
    side: Side,
    mode: str,
    tol_atr: float,
) -> EntryDecision:
    mode_n = str(mode or "pullback").lower()
    if mode_n == "pullback":
        return pullback_entry(df, side=side, tol_atr=tol_atr)
    if mode_n in ("break_retest", "breakretest"):
        return break_retest_entry(df, side=side, tol_atr=tol_atr)
    if mode_n in ("hybrid", "mix"):
        a = pullback_entry(df, side=side, tol_atr=tol_atr)
        if a.ok:
            return a
        b = break_retest_entry(df, side=side, tol_atr=tol_atr)
        return b
    if mode_n in ("mean_reversion", "meanreversion", "mr"):
        return mean_reversion_entry(df, side=side, dist_atr=1.0, min_reject_wick_ratio=1.0)
    if mode_n in ("regime", "switch"):
        df2 = normalize_ohlcv_keep(df)
        if df2 is None or df2.empty:
            return EntryDecision(ok=False, kind="regime", details={})
        last = df2.iloc[-1]
        adx_v = float(last.get("adx") or 0.0) if "adx" in df2.columns and pd.notna(last.get("adx")) else 0.0
        comp = float(last.get("ema_compression") or 0.0) if "ema_compression" in df2.columns and pd.notna(last.get("ema_compression")) else 0.0
        slope = float(last.get("slope_score") or 0.0) if "slope_score" in df2.columns and pd.notna(last.get("slope_score")) else 0.0
        trending = (adx_v >= 18.0) and (abs(slope) >= 0.05) and (comp <= 3.0)
        if trending:
            return decide_entry(df2, side=side, mode="hybrid", tol_atr=tol_atr)
        return mean_reversion_entry(df2, side=side, dist_atr=1.0, min_reject_wick_ratio=1.0)
    return EntryDecision(ok=True, kind="none", details={})
