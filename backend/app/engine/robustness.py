from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, List, Tuple

import pandas as pd
import numpy as np

from .naira_engine import NairaConfig, NairaEngine
from .ohlc import normalize_ohlcv
from .tuner import tune_basic
from ..core.config import settings
from .model import load_model


def walk_forward_backtest(
    engine: NairaEngine,
    symbol: str,
    provider: str,
    base_timeframe: str,
    segments: int = 3,
    min_rows: int = 400,
) -> Dict[str, Any]:
    df = engine.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider)
    df = normalize_ohlcv(df)
    if df.empty or len(df) < int(min_rows):
        return {"error": "insufficient_data", "rows": int(len(df))}
    n = int(len(df))
    segs = max(2, int(segments))
    step = n // segs
    out = []
    for i in range(segs):
        a = i * step
        b = n if i == (segs - 1) else (i + 1) * step
        part = df.iloc[a:b].copy()
        if len(part) < int(min_rows // 2):
            continue
        tmp_path = os.path.join(engine.csv.base_dir, "datasets", "wf", f"{symbol}_{provider}_{base_timeframe}_{i}.csv")
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        part.to_csv(tmp_path, index=False)
        r = engine.backtest(symbol=symbol, provider="csv", base_timeframe=base_timeframe, csv_path=tmp_path)
        out.append({"segment": i, "start": str(part["datetime"].iloc[0]), "end": str(part["datetime"].iloc[-1]), "metrics": r.get("metrics")})
    return {"symbol": symbol, "provider": provider, "base_timeframe": base_timeframe, "segments": out}


def walk_forward_optimize(
    engine: NairaEngine,
    symbol: str,
    provider: str,
    base_timeframe: str,
    segments: int = 4,
    tune_iters: int = 40,
    min_rows: int = 500,
    min_trades: int = 5,
    market_family: str = "crypto",
) -> Dict[str, Any]:
    df = engine.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider)
    df = normalize_ohlcv(df)
    if df.empty or len(df) < int(min_rows):
        return {"error": "insufficient_data", "rows": int(len(df))}
    n = int(len(df))
    segs = max(3, int(segments))
    step = n // segs
    out: List[Dict[str, Any]] = []
    base_dir = os.path.join(engine.csv.base_dir, "datasets", "wf_opt")
    os.makedirs(base_dir, exist_ok=True)
    for i in range(segs - 1):
        a0 = i * step
        a1 = (i + 1) * step
        b0 = a1
        b1 = n if (i + 2) >= segs else (i + 2) * step
        train = df.iloc[a0:a1].copy()
        test = df.iloc[b0:b1].copy()
        if len(train) < int(min_rows // 2) or len(test) < int(min_rows // 2):
            continue
        train_path = os.path.join(base_dir, f"{symbol}_{provider}_{base_timeframe}_train_{i}.csv")
        test_path = os.path.join(base_dir, f"{symbol}_{provider}_{base_timeframe}_test_{i}.csv")
        train.to_csv(train_path, index=False)
        test.to_csv(test_path, index=False)
        tune = tune_basic(
            data_dir=engine.csv.base_dir,
            symbol=symbol,
            provider="csv",
            base_timeframe=base_timeframe,
            csv_path=train_path,
            max_iters=int(tune_iters),
            min_trades=int(min_trades),
            market_family=str(market_family or ""),
        )
        best = tune.get("best_params") or {}
        cfg = NairaConfig(**best) if isinstance(best, dict) else NairaConfig()
        eng = NairaEngine(data_dir=engine.csv.base_dir, config=cfg)
        res = eng.backtest(symbol=symbol, provider="csv", base_timeframe=base_timeframe, csv_path=test_path)
        out.append(
            {
                "fold": i,
                "train": {"start": str(train["datetime"].iloc[0]), "end": str(train["datetime"].iloc[-1]), "rows": int(len(train)), "path": train_path},
                "test": {"start": str(test["datetime"].iloc[0]), "end": str(test["datetime"].iloc[-1]), "rows": int(len(test)), "path": test_path},
                "best_params": best,
                "test_metrics": res.get("metrics"),
            }
        )
    return {"symbol": symbol, "provider": provider, "base_timeframe": base_timeframe, "folds": out}


def walk_forward_threshold_selection(
    engine: NairaEngine,
    symbol: str,
    provider: str,
    base_timeframe: str,
    segments: int = 4,
    thresholds: List[float] | None = None,
    min_trades: int = 20,
) -> Dict[str, Any]:
    thr = thresholds or [0.50, 0.55, 0.60, 0.65, 0.70]
    df = engine.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider)
    df = normalize_ohlcv(df)
    if df.empty or len(df) < 800:
        return {"error": "insufficient_data", "rows": int(len(df))}
    r = engine.backtest(symbol=symbol, provider=provider, base_timeframe=base_timeframe, trades_limit=0, collect_signal_stats=False)
    trades = r.get("trades") or []
    if not trades:
        return {"error": "no_trades"}
    model_path = os.path.join(settings.MODELS_DIR, "naira_logreg.json")
    m = load_model(model_path)
    if m is None:
        return {"error": "model_not_found", "model_path": model_path}
    for t in trades:
        feats = t.get("_features") or {}
        try:
            t["_p"] = float(m.predict_proba({k: float(feats.get(k) or 0.0) for k in m.feature_names}))
        except Exception:
            t["_p"] = 0.0
    times = pd.to_datetime(df["datetime"])
    n = int(len(times))
    segs = max(3, int(segments))
    step = n // segs
    folds = []
    for i in range(segs - 1):
        a0 = i * step
        a1 = (i + 1) * step
        b0 = a1
        b1 = n if (i + 2) >= segs else (i + 2) * step
        t_train0 = times.iloc[a0]
        t_train1 = times.iloc[a1 - 1]
        t_test0 = times.iloc[b0]
        t_test1 = times.iloc[b1 - 1]
        train_trades = [x for x in trades if pd.to_datetime(x.get("entry_time")) >= t_train0 and pd.to_datetime(x.get("entry_time")) <= t_train1]
        test_trades = [x for x in trades if pd.to_datetime(x.get("entry_time")) >= t_test0 and pd.to_datetime(x.get("entry_time")) <= t_test1]
        if len(train_trades) < int(min_trades) or len(test_trades) < int(min_trades):
            continue

        def score_for(th: float, ts: List[Dict[str, Any]]) -> Dict[str, Any]:
            sel = [x for x in ts if float(x.get("_p") or 0.0) >= float(th)]
            if not sel:
                return {"n": 0, "pf": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}
            pnls = [float(x.get("pnl") or 0.0) for x in sel]
            gp = sum(x for x in pnls if x > 0)
            gl = -sum(x for x in pnls if x < 0)
            pf = float(gp / max(1e-9, gl))
            return {"n": int(len(pnls)), "pf": pf, "avg_pnl": float(np.mean(pnls)), "total_pnl": float(np.sum(pnls))}

        best_th = float(thr[0])
        best_pf = -1e9
        best_train = None
        for th in thr:
            met = score_for(float(th), train_trades)
            if met["n"] < int(min_trades):
                continue
            if float(met["pf"]) > float(best_pf):
                best_pf = float(met["pf"])
                best_th = float(th)
                best_train = met
        if best_train is None:
            continue
        test_met = score_for(best_th, test_trades)
        folds.append(
            {
                "fold": i,
                "train": {"start": str(t_train0), "end": str(t_train1), "trades": int(len(train_trades)), "best_th": float(best_th), "metrics": best_train},
                "test": {"start": str(t_test0), "end": str(t_test1), "trades": int(len(test_trades)), "metrics": test_met},
            }
        )
    return {"symbol": symbol, "provider": provider, "base_timeframe": base_timeframe, "model_path": model_path, "thresholds": thr, "folds": folds}

def sensitivity_grid(
    data_dir: str,
    symbol: str,
    provider: str,
    base_timeframe: str,
    csv_path: str | None,
    grid: Dict[str, List[Any]],
    max_rows: int = 250,
) -> Dict[str, Any]:
    base_engine = NairaEngine(data_dir=data_dir)
    results: List[Dict[str, Any]] = []
    keys = list(grid.keys())
    if not keys:
        return {"error": "empty_grid"}

    def rec(i: int, cur: Dict[str, Any]):
        if len(results) >= int(max_rows):
            return
        if i >= len(keys):
            cfg_kwargs = dict(cur)
            cfg = NairaConfig(**cfg_kwargs)
            eng = NairaEngine(data_dir=data_dir, config=cfg)
            r = eng.backtest(symbol=symbol, provider=provider, base_timeframe=base_timeframe, csv_path=csv_path)
            results.append({"params": cfg_kwargs, "metrics": r.get("metrics")})
            return
        k = keys[i]
        for v in grid[k]:
            cur[k] = v
            rec(i + 1, cur)

    rec(0, {})
    return {"symbol": symbol, "provider": provider, "base_timeframe": base_timeframe, "rows": len(results), "results": results}
