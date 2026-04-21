from __future__ import annotations

import random
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from .naira_engine import NairaConfig, NairaEngine


def _score_metrics(metrics: Dict[str, Any], min_trades: int) -> float:
    trades = int(metrics.get("trades") or 0)
    if trades < int(min_trades):
        return -1e9
    pf = float(metrics.get("profit_factor") or 0.0)
    cagr = float(metrics.get("CAGR_pct") or 0.0)
    dd = float(metrics.get("max_drawdown_pct") or 0.0)
    pf_cap = min(pf, 5.0)
    return pf_cap * 50.0 + cagr - abs(dd) * 2.0


def tune_basic(
    data_dir: str,
    symbol: str,
    provider: str,
    base_timeframe: str,
    csv_path: str | None = None,
    max_iters: int = 60,
    seed: int = 7,
    min_trades: int = 5,
    market_family: str = "",
) -> Dict[str, Any]:
    grid = {
        "alignment_threshold": [0.6, 0.7, 0.8],
        "adx_threshold": [15.0, 18.0, 22.0],
        "slope_window_bars": [8, 12, 16],
        "slope_threshold_pct": [0.02, 0.05],
        "sl_atr_mult": [1.0, 1.2, 1.5],
        "tp_atr_mult": [1.5, 2.0, 2.5],
    }
    fam = str(market_family or "").strip().lower()
    if fam in ("fx", "forex"):
        grid["adx_threshold"] = [14.0, 18.0, 22.0]
        grid["slope_threshold_pct"] = [0.01, 0.02, 0.03]
        grid["sl_atr_mult"] = [0.9, 1.1, 1.3]
        grid["tp_atr_mult"] = [1.2, 1.6, 2.0]
    elif fam in ("xau", "metals", "metal", "gold"):
        grid["adx_threshold"] = [16.0, 20.0, 24.0]
        grid["slope_threshold_pct"] = [0.02, 0.04, 0.06]
        grid["sl_atr_mult"] = [1.1, 1.3, 1.6]
        grid["tp_atr_mult"] = [1.6, 2.1, 2.8]
    elif fam in ("crypto", "binance"):
        grid["adx_threshold"] = [16.0, 20.0, 26.0]
        grid["slope_threshold_pct"] = [0.02, 0.05, 0.08]
        grid["sl_atr_mult"] = [1.0, 1.3, 1.7]
        grid["tp_atr_mult"] = [1.6, 2.2, 3.0]
    keys = list(grid.keys())
    all_choices: List[Tuple[Any, ...]] = []
    for a in grid[keys[0]]:
        for b in grid[keys[1]]:
            for c in grid[keys[2]]:
                for d in grid[keys[3]]:
                    for e in grid[keys[4]]:
                        for f in grid[keys[5]]:
                            all_choices.append((a, b, c, d, e, f))
    rnd = random.Random(int(seed))
    rnd.shuffle(all_choices)
    all_choices = all_choices[: int(max_iters)]

    best_score = -1e9
    best_cfg: Optional[NairaConfig] = None
    best_metrics: Optional[Dict[str, Any]] = None
    tried = 0
    for vals in all_choices:
        tried += 1
        cfg = NairaConfig(
            alignment_threshold=float(vals[0]),
            adx_threshold=float(vals[1]),
            slope_window_bars=int(vals[2]),
            slope_threshold_pct=float(vals[3]),
            sl_atr_mult=float(vals[4]),
            tp_atr_mult=float(vals[5]),
        )
        eng = NairaEngine(data_dir=data_dir, config=cfg)
        res = eng.backtest(symbol=symbol, provider=provider, base_timeframe=base_timeframe, csv_path=csv_path)
        met = res.get("metrics") or {}
        sc = _score_metrics(met, min_trades=min_trades)
        if sc > best_score:
            best_score = sc
            best_cfg = cfg
            best_metrics = met

    return {
        "symbol": symbol,
        "provider": provider,
        "base_timeframe": base_timeframe,
        "market_family": fam,
        "tried": tried,
        "best_score": best_score,
        "best_params": asdict(best_cfg) if best_cfg else None,
        "best_metrics": best_metrics,
    }


def tune_ensemble_weights(
    data_dir: str,
    symbols: List[str],
    provider: str,
    base_timeframe: str,
    max_iters: int = 60,
    seed: int = 7,
    max_bars: int = 8000,
    max_positions: int = 2,
    min_trades: int = 20,
) -> Dict[str, Any]:
    syms = [str(s).strip() for s in (symbols or []) if str(s).strip()]
    if not syms:
        return {"error": "no_symbols"}
    rnd = random.Random(int(seed))
    best_score = -1e9
    best_cfg: Optional[NairaConfig] = None
    best_metrics: Optional[Dict[str, Any]] = None
    tried = 0
    for _ in range(int(max_iters)):
        tried += 1
        w_conf = float(rnd.uniform(0.3, 0.9))
        w_ai = float(rnd.uniform(0.0, 0.7))
        w_al = float(rnd.uniform(0.0, 0.2))
        w_sl = float(rnd.uniform(0.0, 0.2))
        w_adx = float(rnd.uniform(0.0, 0.2))
        cfg = NairaConfig(
            ensemble_w_conf=w_conf,
            ensemble_w_ai=w_ai,
            ensemble_w_alignment=w_al,
            ensemble_w_slope=w_sl,
            ensemble_w_adx=w_adx,
        )
        eng = NairaEngine(data_dir=data_dir, config=cfg)
        res = eng.portfolio_backtest(
            symbols=syms,
            provider=provider,
            base_timeframe=base_timeframe,
            max_bars=int(max_bars),
            max_positions=int(max_positions),
            sizing_mode="fixed_risk",
            risk_per_trade_pct=1.0,
            ai_assisted_sizing=True,
            fee_bps=2.0,
        )
        met = res.get("metrics") or {}
        sc = _score_metrics(met, min_trades=min_trades)
        if sc > best_score:
            best_score = sc
            best_cfg = cfg
            best_metrics = met
    return {
        "symbols": syms,
        "provider": provider,
        "base_timeframe": base_timeframe,
        "tried": tried,
        "best_score": best_score,
        "best_weights": asdict(best_cfg) if best_cfg else None,
        "best_metrics": best_metrics,
    }
