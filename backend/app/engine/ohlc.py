from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd


@dataclass(frozen=True)
class OHLCVSpec:
    datetime_col: str = "datetime"
    open_col: str = "open"
    high_col: str = "high"
    low_col: str = "low"
    close_col: str = "close"
    volume_col: str = "volume"


TF_TO_PANDAS_RULE: Dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "1W",
}


def normalize_ohlcv(df: pd.DataFrame, spec: Optional[OHLCVSpec] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    spec = spec or OHLCVSpec()
    out = df.copy()
    cols_lower = {c.lower(): c for c in out.columns}
    if spec.datetime_col not in out.columns:
        if "datetime" in cols_lower:
            out.rename(columns={cols_lower["datetime"]: "datetime"}, inplace=True)
        elif "time" in cols_lower:
            out.rename(columns={cols_lower["time"]: "datetime"}, inplace=True)
        elif "timestamp" in cols_lower:
            out.rename(columns={cols_lower["timestamp"]: "datetime"}, inplace=True)
    if "datetime" in out.columns:
        out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    for k in ("open", "high", "low", "close", "volume"):
        if k not in out.columns and k in cols_lower:
            out.rename(columns={cols_lower[k]: k}, inplace=True)
        cap = k.capitalize()
        if k not in out.columns and cap in out.columns:
            out.rename(columns={cap: k}, inplace=True)
    if "tick_volume" in out.columns and "volume" not in out.columns:
        out.rename(columns={"tick_volume": "volume"}, inplace=True)
    for k in ("open", "high", "low", "close", "volume"):
        if k in out.columns:
            out[k] = pd.to_numeric(out[k], errors="coerce")
    out = out.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime").drop_duplicates(subset=["datetime"])
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    tmp = normalize_ohlcv(df).set_index("datetime").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = tmp.resample(rule).agg(agg).dropna().reset_index()
    return normalize_ohlcv(out)


def validate_ohlcv(df: pd.DataFrame) -> dict:
    df = normalize_ohlcv(df)
    if df.empty:
        return {"ok": False, "rows": 0, "issues": ["empty"]}
    dt = pd.to_datetime(df["datetime"], errors="coerce")
    issues = []
    if dt.isna().any():
        issues.append("invalid_datetime")
    if not dt.is_monotonic_increasing:
        issues.append("not_sorted")
    dups = int(dt.duplicated().sum())
    if dups > 0:
        issues.append(f"duplicates:{dups}")
    gaps = 0
    if len(dt) >= 3:
        diffs = dt.diff().dropna()
        med = diffs.median()
        if pd.notna(med) and med.total_seconds() > 0:
            gaps = int((diffs > (med * 3)).sum())
            if gaps > 0:
                issues.append(f"gaps:{gaps}")
    return {"ok": len(issues) == 0, "rows": int(len(df)), "issues": issues}
