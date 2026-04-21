import os

from fastapi import APIRouter, Query, Header, HTTPException

from ....core.config import settings
from ....engine.naira_engine import NairaConfig, NairaEngine
from ....engine.tuner import tune_basic, tune_ensemble_weights
from ....engine.watchlist import WatchlistStore
from ....services.scanner_service import scanner_singleton
from ....engine.dataset import build_trade_dataset, FEATURES
from ....engine.model import train_logreg_sgd, train_logreg_sgd_multi, load_model
from ....engine.robustness import walk_forward_backtest, walk_forward_optimize, walk_forward_threshold_selection, sensitivity_grid
from ....engine.calibration import calibration_report, calibration_report_by_regime
from ....engine.risk_controls import RiskStore, RiskManager, RiskLimits
from ....schemas.naira import BacktestOut, SignalOut
from ....services.notifier_service import notifier_singleton


router = APIRouter(prefix="/naira", tags=["naira"])
engine = NairaEngine(data_dir=settings.DATA_DIR)
engine.load_model(os.path.join(settings.MODELS_DIR, "naira_logreg.json"))
watchlist_store = WatchlistStore(path=settings.WATCHLIST_PATH)
scanner = scanner_singleton
risk = RiskManager(store=RiskStore(path=settings.RISK_LIMITS_PATH))

def _tier(api_key: str | None) -> str:
    k = (api_key or "").strip()
    if settings.API_KEY_TRADER and k == settings.API_KEY_TRADER:
        return "TRADER"
    if settings.API_KEY_PRO and k == settings.API_KEY_PRO:
        return "PRO"
    return "FREE"


def _require_trader(api_key: str | None) -> None:
    if _tier(api_key) != "TRADER":
        raise HTTPException(status_code=403, detail="requires_trader")


@router.get("/signal", response_model=SignalOut)
def signal(
    symbol: str = Query(...),
    base_timeframe: str = Query("1h"),
    provider: str = Query("csv"),
    csv_path: str | None = Query(None),
    include_debug: bool = Query(False),
    notify: bool = Query(False),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    tier = _tier(api_key)
    if tier != "FREE":
        ok, reason = risk.allow_signal(api_key or "anon")
        if not ok:
            raise HTTPException(status_code=429, detail=reason)
    if tier == "FREE":
        tfs = ["4h", "1d", base_timeframe]
        include_debug = False
    else:
        tfs = ["1w", "1d", "4h", base_timeframe, "30m", "15m", "5m", "1m"]
    out = engine.analyze(
        symbol=symbol,
        provider=provider,
        base_timeframe=base_timeframe,
        csv_path=csv_path,
        timeframes=tfs,
        include_debug=include_debug,
    )
    if notify and tier == "TRADER":
        ok, reason = risk.allow_notify(api_key or "anon")
        if not ok:
            raise HTTPException(status_code=429, detail=reason)
        try:
            notifier_singleton.notify("signal", out)
        except Exception:
            pass
    return out


@router.get("/scan", response_model=list[SignalOut])
def scan(
    symbols: str | None = Query(None),
    base_timeframe: str = Query("1h"),
    provider: str = Query("csv"),
    top: int = Query(10, ge=1, le=200),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    tier = _tier(api_key)
    raw = (symbols or settings.DEFAULT_WATCHLIST or "").strip()
    if not raw:
        return []
    items = [s.strip() for s in raw.split(",") if s.strip()]
    items = items[: int(settings.MAX_SCAN_SYMBOLS)]
    if tier == "FREE":
        tfs = ["4h", "1d", base_timeframe]
    else:
        tfs = ["1w", "1d", "4h", base_timeframe, "30m", "15m", "5m", "1m"]
    out = []
    for sym in items:
        try:
            out.append(engine.analyze(symbol=sym, provider=provider, base_timeframe=base_timeframe, timeframes=tfs))
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
    return out[: int(top)]


@router.post("/backtest", response_model=BacktestOut)
def backtest(payload: dict):
    symbol = payload.get("symbol")
    if not symbol:
        return {
            "symbol": "",
            "provider": "csv",
            "base_timeframe": "",
            "start": "",
            "end": "",
            "metrics": {"error": "symbol es obligatorio"},
            "trades": [],
        }
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    csv_path = payload.get("csv_path")
    max_bars = payload.get("max_bars")
    max_bars_v = int(max_bars) if max_bars is not None else None
    starting_cash = float(payload.get("starting_cash") or 10000.0)
    fee_bps = float(payload.get("fee_bps") or 0.0)
    slippage_bps = float(payload.get("slippage_bps") or 0.0)
    slippage_atr_pct_mult = float(payload.get("slippage_atr_pct_mult") or 0.0)
    max_participation_pct = float(payload.get("max_participation_pct") or 0.10)
    trades_limit = int(payload.get("trades_limit") or 200)
    sizing_mode = str(payload.get("sizing_mode") or "fixed_qty")
    fixed_qty = float(payload.get("fixed_qty") or 1.0)
    risk_per_trade_pct = float(payload.get("risk_per_trade_pct") or 1.0)
    max_leverage = float(payload.get("max_leverage") or 1.0)
    ai_assisted_sizing = bool(payload.get("ai_assisted_sizing") or False)
    ai_risk_min_pct = float(payload.get("ai_risk_min_pct") or 0.25)
    ai_risk_max_pct = float(payload.get("ai_risk_max_pct") or 1.5)
    martingale_mult = float(payload.get("martingale_mult") or 2.0)
    martingale_max_steps = int(payload.get("martingale_max_steps") or 3)
    collect_signal_stats = bool(payload.get("collect_signal_stats") or False)
    bar_magnifier = bool(payload.get("bar_magnifier") or False)
    magnifier_timeframe = str(payload.get("magnifier_timeframe") or "1m")
    entry_magnifier = bool(payload.get("entry_magnifier") or False)
    entry_magnifier_timeframe = str(payload.get("entry_magnifier_timeframe") or "5m")
    cfg_overrides = payload.get("config") or None
    model_path = payload.get("model_path")
    eng = engine
    if isinstance(cfg_overrides, dict) and cfg_overrides:
        try:
            eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(**cfg_overrides))
        except Exception:
            eng = engine
    if model_path and isinstance(model_path, str) and os.path.exists(model_path):
        try:
            eng.load_model(model_path)
        except Exception:
            pass
    result = eng.backtest(
        symbol=str(symbol),
        provider=provider,
        base_timeframe=base_timeframe,
        csv_path=str(csv_path) if csv_path else None,
        max_bars=max_bars_v,
        starting_cash=starting_cash,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        slippage_atr_pct_mult=slippage_atr_pct_mult,
        max_participation_pct=max_participation_pct,
        trades_limit=trades_limit,
        sizing_mode=sizing_mode,
        fixed_qty=fixed_qty,
        risk_per_trade_pct=risk_per_trade_pct,
        max_leverage=max_leverage,
        ai_assisted_sizing=ai_assisted_sizing,
        ai_risk_min_pct=ai_risk_min_pct,
        ai_risk_max_pct=ai_risk_max_pct,
        martingale_mult=martingale_mult,
        martingale_max_steps=martingale_max_steps,
        collect_signal_stats=collect_signal_stats,
        bar_magnifier=bar_magnifier,
        magnifier_timeframe=magnifier_timeframe,
        entry_magnifier=entry_magnifier,
        entry_magnifier_timeframe=entry_magnifier_timeframe,
    )
    if "error" in result:
        return {
            "symbol": str(symbol),
            "provider": provider,
            "base_timeframe": base_timeframe,
            "start": "",
            "end": "",
            "metrics": {"error": str(result.get("error"))},
            "trades": [],
        }
    return result


@router.post("/portfolio/backtest")
def portfolio_backtest(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbols = payload.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    if not isinstance(symbols, list) or not symbols:
        raise HTTPException(status_code=400, detail="symbols is required")
    provider = str(payload.get("provider") or "binance")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    starting_cash = float(payload.get("starting_cash") or 10000.0)
    fee_bps = float(payload.get("fee_bps") or 0.0)
    max_bars = payload.get("max_bars")
    max_bars_v = int(max_bars) if max_bars is not None else None
    max_positions = int(payload.get("max_positions") or 3)
    cooldown_bars = int(payload.get("per_symbol_cooldown_bars") or 0)
    sizing_mode = str(payload.get("sizing_mode") or "fixed_risk")
    risk_per_trade_pct = float(payload.get("risk_per_trade_pct") or 1.0)
    max_leverage = float(payload.get("max_leverage") or 1.0)
    ai_assisted_sizing = bool(payload.get("ai_assisted_sizing") if payload.get("ai_assisted_sizing") is not None else True)
    ai_risk_min_pct = float(payload.get("ai_risk_min_pct") or 0.25)
    ai_risk_max_pct = float(payload.get("ai_risk_max_pct") or 1.5)
    bar_magnifier = bool(payload.get("bar_magnifier") or False)
    magnifier_timeframe = str(payload.get("magnifier_timeframe") or "5m")
    cfg_overrides = payload.get("config") or None
    eng = engine
    if isinstance(cfg_overrides, dict) and cfg_overrides:
        try:
            eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(**cfg_overrides))
        except Exception:
            eng = engine
    return eng.portfolio_backtest(
        symbols=[str(s) for s in symbols],
        provider=provider,
        base_timeframe=base_timeframe,
        starting_cash=starting_cash,
        fee_bps=fee_bps,
        max_bars=max_bars_v,
        max_positions=max_positions,
        per_symbol_cooldown_bars=cooldown_bars,
        sizing_mode=sizing_mode,
        risk_per_trade_pct=risk_per_trade_pct,
        max_leverage=max_leverage,
        ai_assisted_sizing=ai_assisted_sizing,
        ai_risk_min_pct=ai_risk_min_pct,
        ai_risk_max_pct=ai_risk_max_pct,
        bar_magnifier=bar_magnifier,
        magnifier_timeframe=magnifier_timeframe,
    )


@router.get("/watchlist")
def get_watchlist():
    return {"symbols": watchlist_store.load()}


@router.put("/watchlist")
def put_watchlist(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbols = payload.get("symbols") or []
    if not isinstance(symbols, list):
        raise HTTPException(status_code=400, detail="symbols must be a list")
    watchlist_store.save([str(s) for s in symbols])
    return {"status": "ok", "symbols": watchlist_store.load()}


@router.get("/scan/status")
def scan_status():
    st = scanner.status
    return {
        "last_run_ts": st.last_run_ts,
        "last_duration_ms": st.last_duration_ms,
        "last_error": st.last_error,
        "last_top": st.last_top or [],
    }


@router.get("/alerts")
def alerts(limit: int = Query(50, ge=1, le=500)):
    return {"alerts": scanner.get_alerts(limit=int(limit))}


@router.post("/tune")
def tune(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    market_family = str(payload.get("market_family") or "")
    csv_path = payload.get("csv_path")
    max_iters = int(payload.get("max_iters") or 60)
    min_trades = int(payload.get("min_trades") or 5)
    seed = int(payload.get("seed") or 7)
    return tune_basic(
        data_dir=settings.DATA_DIR,
        symbol=str(symbol),
        provider=provider,
        base_timeframe=base_timeframe,
        csv_path=str(csv_path) if csv_path else None,
        max_iters=max_iters,
        min_trades=min_trades,
        seed=seed,
        market_family=market_family,
    )


@router.post("/ensemble/tune")
def ensemble_tune(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbols = payload.get("symbols") or []
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    provider = str(payload.get("provider") or "binance")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    max_iters = int(payload.get("max_iters") or 60)
    seed = int(payload.get("seed") or 7)
    max_bars = int(payload.get("max_bars") or 8000)
    max_positions = int(payload.get("max_positions") or 2)
    min_trades = int(payload.get("min_trades") or 20)
    return tune_ensemble_weights(
        data_dir=settings.DATA_DIR,
        symbols=[str(s) for s in symbols],
        provider=provider,
        base_timeframe=base_timeframe,
        max_iters=max_iters,
        seed=seed,
        max_bars=max_bars,
        max_positions=max_positions,
        min_trades=min_trades,
    )


@router.post("/dataset/build")
def dataset_build(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    name = str(payload.get("name") or f"{symbol}_{provider}_{base_timeframe}".replace("/", ""))
    max_bars = int(payload.get("max_bars") or 6000)
    out_path = os.path.join(settings.DATASETS_DIR, f"{name}.csv")
    r = build_trade_dataset(engine, symbol=str(symbol), provider=provider, base_timeframe=base_timeframe, out_path=out_path, max_bars=max_bars)
    return {"path": r.path, "rows": r.rows, "features": FEATURES}


@router.get("/model/status")
def model_status():
    model_path = os.path.join(settings.MODELS_DIR, "naira_logreg.json")
    m = load_model(model_path)
    return {"path": model_path, "loaded": bool(m is not None), "features": (m.feature_names if m else [])}


@router.post("/model/calibrate")
def model_calibrate(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    dataset_path = payload.get("dataset_path")
    if not dataset_path:
        raise HTTPException(status_code=400, detail="dataset_path is required")
    bins = int(payload.get("bins") or 10)
    by_regime = bool(payload.get("by_regime") or False)
    regime_feature = str(payload.get("regime_feature") or "adx")
    cut1 = float(payload.get("cut1") or 18.0)
    cut2 = float(payload.get("cut2") or 25.0)
    model_path = os.path.join(settings.MODELS_DIR, "naira_logreg.json")
    if by_regime:
        return calibration_report_by_regime(dataset_csv=str(dataset_path), model_path=model_path, bins=bins, regime_feature=regime_feature, cut1=cut1, cut2=cut2)
    return calibration_report(dataset_csv=str(dataset_path), model_path=model_path, bins=bins)


@router.get("/risk/status")
def risk_status(api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    return risk.status(api_key or "anon")


@router.get("/risk/limits")
def risk_limits_get(api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    return risk.store.load().__dict__


@router.put("/risk/limits")
def risk_limits_put(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    try:
        lim = RiskLimits(**payload)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid limits")
    risk.store.save(lim)
    return lim.__dict__


@router.post("/model/train")
def model_train(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    dataset_path = payload.get("dataset_path")
    if not dataset_path:
        raise HTTPException(status_code=400, detail="dataset_path is required")
    model_path = os.path.join(settings.MODELS_DIR, "naira_logreg.json")
    lr = float(payload.get("lr") or 0.15)
    epochs = int(payload.get("epochs") or 200)
    l2 = float(payload.get("l2") or 0.001)
    seed = int(payload.get("seed") or 7)
    tr = train_logreg_sgd(
        dataset_csv=str(dataset_path),
        feature_names=FEATURES,
        out_path=model_path,
        lr=lr,
        epochs=epochs,
        l2=l2,
        seed=seed,
    )
    engine.load_model(model_path)
    scanner.reload_model()
    return {"model_path": tr.path, "rows": tr.rows, "accuracy": tr.accuracy, "features": tr.feature_names}


@router.post("/model/stack/train")
def model_stack_train(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    dataset_paths = payload.get("dataset_paths") or []
    if isinstance(dataset_paths, str):
        dataset_paths = [s.strip() for s in dataset_paths.split(",") if s.strip()]
    if not isinstance(dataset_paths, list) or not dataset_paths:
        raise HTTPException(status_code=400, detail="dataset_paths is required")
    out_name = str(payload.get("model_name") or "naira_logreg_stack.json")
    model_path = os.path.join(settings.MODELS_DIR, out_name)
    lr = float(payload.get("lr") or 0.15)
    epochs = int(payload.get("epochs") or 200)
    l2 = float(payload.get("l2") or 0.001)
    seed = int(payload.get("seed") or 7)
    tr = train_logreg_sgd_multi(
        dataset_csvs=[str(p) for p in dataset_paths],
        feature_names=FEATURES,
        out_path=model_path,
        lr=lr,
        epochs=epochs,
        l2=l2,
        seed=seed,
    )
    return {"model_path": tr.path, "rows": tr.rows, "accuracy": tr.accuracy, "features": tr.feature_names}


@router.post("/research/late_entry")
def research_late_entry(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "binance")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    max_bars = payload.get("max_bars")
    max_bars_v = int(max_bars) if max_bars is not None else None
    fee_bps = float(payload.get("fee_bps") or 0.0)
    slippage_bps = float(payload.get("slippage_bps") or 0.0)
    slippage_atr_pct_mult = float(payload.get("slippage_atr_pct_mult") or 0.0)
    r = engine.backtest(
        symbol=str(symbol),
        provider=provider,
        base_timeframe=base_timeframe,
        max_bars=max_bars_v,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        slippage_atr_pct_mult=slippage_atr_pct_mult,
        trades_limit=0,
        collect_signal_stats=False,
    )
    met = r.get("metrics") or {}
    return {"late_entry_report": met.get("late_entry_report"), "regime_report": met.get("regime_report")}


@router.post("/research/stress")
def research_stress(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "binance")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    max_bars = payload.get("max_bars")
    max_bars_v = int(max_bars) if max_bars is not None else None
    fee_bps = float(payload.get("fee_bps") or 0.0)
    slippages = payload.get("slippages_bps") or [0.0, 2.0, 5.0]
    out = []
    for sb in slippages:
        try:
            res = engine.backtest(
                symbol=str(symbol),
                provider=provider,
                base_timeframe=base_timeframe,
                max_bars=max_bars_v,
                fee_bps=fee_bps,
                slippage_bps=float(sb),
                trades_limit=0,
            )
            out.append({"slippage_bps": float(sb), "metrics": res.get("metrics")})
        except Exception as e:
            out.append({"slippage_bps": float(sb), "error": str(e)})
    return {"symbol": str(symbol), "provider": provider, "base_timeframe": base_timeframe, "runs": out}

@router.post("/robustness/walk_forward")
def robustness_walk_forward(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    segments = int(payload.get("segments") or 3)
    min_rows = int(payload.get("min_rows") or 400)
    return walk_forward_backtest(engine, symbol=str(symbol), provider=provider, base_timeframe=base_timeframe, segments=segments, min_rows=min_rows)


@router.post("/robustness/walk_forward_optimize")
def robustness_walk_forward_optimize(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    segments = int(payload.get("segments") or 4)
    tune_iters = int(payload.get("tune_iters") or 40)
    min_rows = int(payload.get("min_rows") or 500)
    min_trades = int(payload.get("min_trades") or 5)
    market_family = str(payload.get("market_family") or "crypto")
    return walk_forward_optimize(
        engine,
        symbol=str(symbol),
        provider=provider,
        base_timeframe=base_timeframe,
        segments=segments,
        tune_iters=tune_iters,
        min_rows=min_rows,
        min_trades=min_trades,
        market_family=market_family,
    )


@router.post("/robustness/threshold_selection")
def robustness_threshold_selection(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "binance")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    segments = int(payload.get("segments") or 4)
    thresholds = payload.get("thresholds")
    thr_list = [float(x) for x in thresholds] if isinstance(thresholds, list) else None
    min_trades = int(payload.get("min_trades") or 20)
    return walk_forward_threshold_selection(engine, symbol=str(symbol), provider=provider, base_timeframe=base_timeframe, segments=segments, thresholds=thr_list, min_trades=min_trades)


@router.post("/robustness/sensitivity")
def robustness_sensitivity(payload: dict, api_key: str | None = Header(None, alias="X-API-Key")):
    _require_trader(api_key)
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    provider = str(payload.get("provider") or "csv")
    base_timeframe = str(payload.get("base_timeframe") or "1h")
    csv_path = payload.get("csv_path")
    grid = payload.get("grid") or {}
    max_rows = int(payload.get("max_rows") or 250)
    if not isinstance(grid, dict):
        raise HTTPException(status_code=400, detail="grid must be an object")
    return sensitivity_grid(
        data_dir=settings.DATA_DIR,
        symbol=str(symbol),
        provider=provider,
        base_timeframe=base_timeframe,
        csv_path=str(csv_path) if csv_path else None,
        grid=grid,
        max_rows=max_rows,
    )
