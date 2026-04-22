from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .naira_engine import NairaEngine, NairaConfig


FEATURES = [
    "alignment",
    "slope_score",
    "regression_slope_pct",
    "regression_r2",
    "adx",
    "atr",
    "atr_pct",
    "ema_compression",
    "trend_age_bars",
    "signal_age_bars",
    "dist_ema25_atr",
    "dist_ema80_atr",
    "dist_ema220_atr",
    "dist_reg_atr",
    "hour_utc",
    "is_weekend",
    "dist_pivot_P_atr",
    "nearest_support_distance_atr",
    "nearest_resistance_distance_atr",
    "confluence_levels",
    "confluence_fibo",
    "alligator_mouth",
    "ai_prob_entry",
]


@dataclass(frozen=True)
class DatasetResult:
    path: str
    rows: int


def build_trade_dataset(
    engine: NairaEngine,
    symbol: str,
    provider: str,
    base_timeframe: str,
    out_path: str,
    max_trades: int = 2000,
    max_bars: int = 6000,
) -> DatasetResult:
    def collect(e: NairaEngine) -> List[Dict[str, Any]]:
        res = e.backtest(symbol=symbol, provider=provider, base_timeframe=base_timeframe, max_bars=int(max_bars), feature_mode="fast", apply_execution_gates=False)
        trades = res.get("trades") or []
        out: List[Dict[str, Any]] = []
        for t in trades[-int(max_trades):]:
            feats = t.get("_features") or {}
            if not feats:
                continue
            row: Dict[str, Any] = {k: feats.get(k) for k in FEATURES}
            row["symbol"] = symbol
            row["provider"] = provider
            row["base_timeframe"] = base_timeframe
            row["pnl"] = float(t.get("pnl") or 0.0)
            row["win"] = 1 if float(t.get("pnl") or 0.0) > 0 else 0
            out.append(row)
        return out

    fallback = NairaEngine(data_dir=engine.csv.base_dir, config=NairaConfig(entry_mode="none"))
    rows = collect(fallback)
    if not rows and str(getattr(engine, "config", None) and getattr(engine.config, "entry_mode", "")) != "none":
        rows = collect(engine)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cols = ["symbol", "provider", "base_timeframe", "pnl", "win"] + list(FEATURES)
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(out_path, index=False)
    return DatasetResult(path=out_path, rows=int(len(df)))
