from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd


def classify_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().replace("/", "")
    if s.endswith("USDT") or s.endswith("USD") and len(s) > 6:
        return "crypto"
    if s in ("XAUUSD", "XAGUSD") or s.startswith("XAU") or s.startswith("XAG"):
        return "metals"
    if len(s) == 6 and s.isalpha():
        return "fx"
    return "other"


@dataclass(frozen=True)
class OperationalFilterConfig:
    fx_session_utc: Tuple[int, int] = (6, 21)
    max_atr_pct: float = 4.0
    min_atr_pct: float = 0.02
    news_blackout_path: str = ""
    news_blackout_minutes: int = 30


def _load_blackouts(path: str) -> List[Tuple[datetime, datetime]]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        items = data.get("events") if isinstance(data, dict) else data
        out = []
        for it in items:
            a = pd.to_datetime(it.get("start"), utc=True, errors="coerce")
            b = pd.to_datetime(it.get("end"), utc=True, errors="coerce")
            if pd.notna(a) and pd.notna(b):
                out.append((a.to_pydatetime(), b.to_pydatetime()))
        return out
    except Exception:
        return []


def allow_session(symbol: str, ts: datetime, cfg: OperationalFilterConfig) -> bool:
    kind = classify_symbol(symbol)
    if kind != "fx":
        return True
    t = ts.astimezone(timezone.utc)
    h0, h1 = int(cfg.fx_session_utc[0]), int(cfg.fx_session_utc[1])
    h = int(t.hour)
    return bool(h0 <= h <= h1)


def allow_atr_pct(close: float, atr: float, cfg: OperationalFilterConfig) -> bool:
    c = float(close)
    a = float(atr)
    if c <= 0 or a <= 0:
        return True
    pct = (a / c) * 100.0
    return bool(pct <= float(cfg.max_atr_pct) and pct >= float(cfg.min_atr_pct))


def allow_news(ts: datetime, cfg: OperationalFilterConfig) -> bool:
    if not cfg.news_blackout_path:
        return True
    blackouts = _load_blackouts(cfg.news_blackout_path)
    if not blackouts:
        return True
    t = ts.astimezone(timezone.utc)
    for a, b in blackouts:
        if a <= t <= b:
            return False
    return True


def apply_operational_filters(symbol: str, ts: datetime, close: float, atr: Optional[float], cfg: OperationalFilterConfig) -> List[str]:
    reasons = []
    if not allow_session(symbol, ts, cfg):
        reasons.append("Filtro sesión (FX)")
    if atr is not None and not allow_atr_pct(close, float(atr), cfg):
        reasons.append("Filtro ATR% (proxy spread/vol)")
    if not allow_news(ts, cfg):
        reasons.append("Filtro news blackout")
    return reasons
