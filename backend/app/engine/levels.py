from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .ohlc import normalize_ohlcv, resample_ohlcv


def pivot_points_prev_day(df: pd.DataFrame) -> Dict[str, float]:
    df = normalize_ohlcv(df)
    if df.empty:
        return {}
    daily = resample_ohlcv(df, "1D")
    if len(daily) < 2:
        return {}
    prev = daily.iloc[-2]
    P = (float(prev["high"]) + float(prev["low"]) + float(prev["close"])) / 3.0
    R1 = 2 * P - float(prev["low"])
    S1 = 2 * P - float(prev["high"])
    R2 = P + (float(prev["high"]) - float(prev["low"]))
    S2 = P - (float(prev["high"]) - float(prev["low"]))
    R3 = float(prev["high"]) + 2 * (P - float(prev["low"]))
    S3 = float(prev["low"]) - 2 * (float(prev["high"]) - P)
    return {"P": P, "R1": R1, "S1": S1, "R2": R2, "S2": S2, "R3": R3, "S3": S3}


def _is_swing_high(high: pd.Series, i: int, lb: int) -> bool:
    a = high.iloc[i - lb : i + lb + 1]
    return bool(len(a) == (2 * lb + 1) and float(high.iloc[i]) == float(a.max()))


def _is_swing_low(low: pd.Series, i: int, lb: int) -> bool:
    a = low.iloc[i - lb : i + lb + 1]
    return bool(len(a) == (2 * lb + 1) and float(low.iloc[i]) == float(a.min()))


def swing_levels(df: pd.DataFrame, lookback: int = 3, max_points: int = 200) -> Tuple[List[float], List[float]]:
    df = normalize_ohlcv(df)
    if df.empty:
        return [], []
    lb = int(lookback)
    highs = df["high"]
    lows = df["low"]
    res_h = []
    res_l = []
    for i in range(lb, len(df) - lb):
        if _is_swing_high(highs, i, lb):
            res_h.append(float(highs.iloc[i]))
        if _is_swing_low(lows, i, lb):
            res_l.append(float(lows.iloc[i]))
    return res_h[-max_points:], res_l[-max_points:]


def fractals(df: pd.DataFrame, lookback: int = 2) -> pd.DataFrame:
    df = normalize_ohlcv(df)
    if df.empty:
        return pd.DataFrame({"fractal_high": [], "fractal_low": []})
    lb = int(lookback)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    fh = np.zeros(len(df), dtype=bool)
    fl = np.zeros(len(df), dtype=bool)
    for i in range(lb, len(df) - lb):
        w_h = highs[i - lb : i + lb + 1]
        w_l = lows[i - lb : i + lb + 1]
        if float(highs[i]) == float(np.max(w_h)):
            fh[i] = True
        if float(lows[i]) == float(np.min(w_l)):
            fl[i] = True
    return pd.DataFrame({"fractal_high": fh, "fractal_low": fl})


def latest_fractal_levels(df: pd.DataFrame, lookback: int = 2) -> Dict[str, float]:
    df = normalize_ohlcv(df)
    if df.empty:
        return {}
    f = fractals(df, lookback=lookback)
    out: Dict[str, float] = {}
    try:
        idx_h = int(np.where(f["fractal_high"].to_numpy(dtype=bool))[0][-1])
        out["fractal_high"] = float(df["high"].iloc[idx_h])
    except Exception:
        pass
    try:
        idx_l = int(np.where(f["fractal_low"].to_numpy(dtype=bool))[0][-1])
        out["fractal_low"] = float(df["low"].iloc[idx_l])
    except Exception:
        pass
    return out


def fibo_horizontal(df: pd.DataFrame, lookback: int = 120, levels: Tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786)) -> Dict[str, float]:
    df = normalize_ohlcv(df)
    if df.empty:
        return {}
    w = df.iloc[-int(lookback) :] if len(df) > int(lookback) else df
    hi = float(w["high"].max())
    lo = float(w["low"].min())
    rng = hi - lo
    if rng <= 0:
        return {}
    out: Dict[str, float] = {"hi": hi, "lo": lo}
    for lv in levels:
        out[f"ret_{lv}"] = float(hi - rng * float(lv))
        out[f"ext_{lv}"] = float(hi + rng * float(lv))
    out["ext_1.272"] = float(hi + rng * 1.272)
    out["ext_1.618"] = float(hi + rng * 1.618)
    return out


def fibo_vertical_timezones(df: pd.DataFrame, lookback: int = 2, ratios: Tuple[float, ...] = (0.618, 1.0, 1.618, 2.618)) -> List[str]:
    df = normalize_ohlcv(df)
    if df.empty or "datetime" not in df.columns:
        return []
    f = fractals(df, lookback=lookback)
    idxs = sorted(list(np.where((f["fractal_high"] | f["fractal_low"]).to_numpy(dtype=bool))[0]))
    if len(idxs) < 2:
        return []
    i1, i2 = idxs[-2], idxs[-1]
    t1 = pd.to_datetime(df["datetime"].iloc[int(i1)])
    t2 = pd.to_datetime(df["datetime"].iloc[int(i2)])
    dt = t2 - t1
    if dt.total_seconds() <= 0:
        return []
    return [(t2 + (dt * float(r))).isoformat() for r in ratios]


@dataclass(frozen=True)
class ClusteredLevels:
    resistances: List[float]
    supports: List[float]


def cluster_levels(levels: List[float], tolerance: float) -> List[float]:
    if not levels:
        return []
    tol = float(max(1e-9, tolerance))
    xs = sorted(float(x) for x in levels)
    clusters = []
    cur = [xs[0]]
    for x in xs[1:]:
        if abs(x - np.mean(cur)) <= tol:
            cur.append(x)
        else:
            clusters.append(float(np.mean(cur)))
            cur = [x]
    clusters.append(float(np.mean(cur)))
    return clusters


def build_levels(df: pd.DataFrame, atr: float | None = None, lookback: int = 3) -> ClusteredLevels:
    r, s = swing_levels(df, lookback=lookback)
    tol = float(atr * 0.6) if (atr is not None and atr > 0) else float((df["close"].iloc[-1] if not df.empty else 1.0) * 0.002)
    return ClusteredLevels(
        resistances=cluster_levels(r, tolerance=tol),
        supports=cluster_levels(s, tolerance=tol),
    )


def nearest_level_distance(price: float, levels: List[float]) -> float | None:
    if not levels:
        return None
    p = float(price)
    return float(min(abs(p - float(x)) for x in levels))


def confluence_score(price: float, pivots: Dict[str, float], levels: ClusteredLevels, atr: float | None) -> float:
    p = float(price)
    tol = float(atr * 0.8) if (atr is not None and atr > 0) else max(1e-9, p * 0.003)
    hits = 0.0
    total = 0.0
    for k in ("P", "R1", "S1", "R2", "S2"):
        if k in pivots:
            total += 1.0
            if abs(p - float(pivots[k])) <= tol:
                hits += 1.0
    for lvl in (levels.supports + levels.resistances)[:12]:
        total += 0.2
        if abs(p - float(lvl)) <= tol:
            hits += 0.2
    if total <= 0:
        return 0.0
    return float(np.clip(hits / total, 0.0, 1.0))


def fibo_confluence_score(price: float, fibo: Dict[str, float], atr: float | None) -> float:
    if not fibo:
        return 0.0
    p = float(price)
    tol = float(atr * 0.8) if (atr is not None and atr > 0) else max(1e-9, p * 0.003)
    vals = [float(v) for k, v in fibo.items() if k not in ("hi", "lo")]
    if not vals:
        return 0.0
    near = sum(1 for v in vals if abs(p - v) <= tol)
    return float(np.clip(near / max(1, len(vals)), 0.0, 1.0))


def level_relevance(df: pd.DataFrame, levels: List[float], atr: float | None, lookback_bars: int = 200) -> Dict[float, int]:
    df = normalize_ohlcv(df)
    if df.empty or not levels:
        return {}
    w = df.iloc[-int(lookback_bars) :] if len(df) > int(lookback_bars) else df
    tol = float(atr * 0.6) if (atr is not None and atr > 0) else float(w["close"].iloc[-1] * 0.002)
    counts: Dict[float, int] = {}
    hi = w["high"].to_numpy(dtype=float)
    lo = w["low"].to_numpy(dtype=float)
    for lv in levels:
        x = float(lv)
        touched = int(np.sum((lo <= x + tol) & (hi >= x - tol)))
        counts[x] = touched
    return counts


def nearest_levels_summary(df: pd.DataFrame, clustered: ClusteredLevels, price: float, atr: float | None) -> Dict[str, float]:
    df = normalize_ohlcv(df)
    if df.empty:
        return {}
    p = float(price)
    rel_s = level_relevance(df, clustered.supports, atr=atr)
    rel_r = level_relevance(df, clustered.resistances, atr=atr)
    nearest_s = min(clustered.supports, key=lambda x: abs(p - float(x))) if clustered.supports else None
    nearest_r = min(clustered.resistances, key=lambda x: abs(p - float(x))) if clustered.resistances else None
    out: Dict[str, float] = {}
    if nearest_s is not None:
        dist = abs(p - float(nearest_s))
        out["nearest_support"] = float(nearest_s)
        out["nearest_support_distance"] = float(dist)
        out["nearest_support_distance_atr"] = float(dist / float(atr)) if (atr is not None and atr > 0) else 0.0
        out["nearest_support_touches"] = float(rel_s.get(float(nearest_s), 0))
    if nearest_r is not None:
        dist = abs(p - float(nearest_r))
        out["nearest_resistance"] = float(nearest_r)
        out["nearest_resistance_distance"] = float(dist)
        out["nearest_resistance_distance_atr"] = float(dist / float(atr)) if (atr is not None and atr > 0) else 0.0
        out["nearest_resistance_touches"] = float(rel_r.get(float(nearest_r), 0))
    return out
