from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.core.config import settings
from app.engine.calibration import calibration_report
from app.engine.dataset import build_trade_dataset
from app.engine.history_store import HistoryStore
from app.engine.model import train_logreg_sgd_multi
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.multi_brain import run_multi_brain
from app.engine.providers.binance_rest_provider import BinanceRestOHLCVProvider


RUN_TFS = ["5m", "15m", "30m", "1h"]
HT_TFS = ["4h", "1d", "1w"]
DEFAULT_TFS = list(RUN_TFS)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_hms() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")


def _ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read() or "")
    except Exception:
        return default


def _write_json(path: str, obj: Any) -> None:
    _ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def _universe_size() -> int:
    try:
        v = int(os.getenv("PIPELINE_UNIVERSE", "30").strip() or "30")
        return 100 if v >= 100 else 30
    except Exception:
        return 30


def _top_n() -> int:
    try:
        v = int(os.getenv("PIPELINE_TOPN", "10").strip() or "10")
        return max(1, min(100, v))
    except Exception:
        return 10


def _watchlist_path(provider: str) -> str:
    p = str(provider).lower()
    if p == "binance":
        wl = "crypto_top100.json" if _universe_size() >= 100 else "crypto_top30.json"
        return os.path.join(str(settings.DATA_DIR), "watchlists", wl)
    if p == "mt5":
        return os.path.join(str(settings.DATA_DIR), "watchlists", "fx_majors_minors.json")
    return os.path.join(str(settings.DATA_DIR), "watchlists", "default.json")


def load_symbols(provider: str) -> List[str]:
    wl = _watchlist_path(provider)
    obj = _read_json(wl, {})
    items = obj.get("symbols") if isinstance(obj, dict) else obj
    out = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not out and str(provider).lower() == "csv":
        wl2 = os.path.join(str(settings.DATA_DIR), "watchlists", "crypto_top30.json")
        obj2 = _read_json(wl2, {})
        it2 = obj2.get("symbols") if isinstance(obj2, dict) else obj2
        out = [str(x).strip() for x in (it2 or []) if str(x).strip()]
    return out[: _universe_size()]


def pick_top_symbols(scan_items: List[Dict[str, Any]], top_n: int) -> List[str]:
    items = list(scan_items or [])
    items.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
    out = []
    for it in items:
        s = str(it.get("symbol") or "").strip()
        if not s:
            continue
        out.append(s)
        if len(out) >= int(top_n):
            break
    return out


def make_run_dir(provider: str) -> str:
    base = os.path.join(str(settings.DATA_DIR), "reports", _utc_day(), f"run_{_utc_hms()}_{str(provider).lower()}")
    return _ensure_dir(base)


def _timeframe_window_days(tf: str) -> int:
    t = str(tf)
    if t == "5m":
        return 14
    if t == "15m":
        return 45
    if t == "30m":
        return 90
    if t == "1h":
        return 180
    if t == "4h":
        return 365
    if t == "1d":
        return 365 * 3
    if t == "1w":
        return 365 * 7
    return 365


def cmd_data_update(provider: str, run_dir: str, symbols: List[str], tfs: List[str], update_workers: int) -> Dict[str, Any]:
    p = str(provider).lower()
    store = HistoryStore(base_dir=str(settings.DATA_DIR))
    updated = 0
    errors: List[str] = []
    if p in ("binance", "csv"):
        ex = BinanceRestOHLCVProvider()
        def _update_one(sym: str, tf: str) -> tuple[bool, Optional[str]]:
            try:
                latest = store.latest_datetime(provider="csv", symbol=sym, timeframe=tf)
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=_timeframe_window_days(tf))
                since_ms = int(start.timestamp() * 1000)
                if latest is not None:
                    try:
                        since_ms = int(pd.to_datetime(latest).timestamp() * 1000) - 1
                    except Exception:
                        since_ms = since_ms
                chunks = []
                cur = int(since_ms)
                for _ in range(50):
                    df = ex.get_ohlc(symbol=sym, timeframe=tf, limit=1000, since_ms=cur)
                    if df is None or df.empty:
                        break
                    chunks.append(df)
                    last_dt = pd.to_datetime(df["datetime"].iloc[-1])
                    nxt = int(last_dt.timestamp() * 1000) + 1
                    if nxt <= cur:
                        break
                    cur = nxt
                    if len(df) < 1000:
                        break
                if not chunks:
                    return (False, None)
                df_all = pd.concat(chunks).drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
                try:
                    store.upsert(provider="binance", symbol=sym, timeframe=tf, df=df_all)
                except Exception:
                    pass
                store.upsert(provider="csv", symbol=sym, timeframe=tf, df=df_all)
                return (True, None)
            except Exception as e:
                return (False, f"{sym}:{tf}:{type(e).__name__}")

        w = int(max(1, int(update_workers)))
        if w <= 1:
            for sym in symbols:
                for tf in tfs:
                    ok, err = _update_one(sym, tf)
                    if ok:
                        updated += 1
                    if err:
                        errors.append(err)
        else:
            with ThreadPoolExecutor(max_workers=w) as pool:
                futs = [pool.submit(_update_one, sym, tf) for sym in symbols for tf in tfs]
                for f in as_completed(futs):
                    ok, err = f.result()
                    if ok:
                        updated += 1
                    if err:
                        errors.append(err)
    elif p == "mt5":
        try:
            from app.engine.providers.mt5_provider import MT5OHLCVProvider

            mt5 = MT5OHLCVProvider()
            for sym in symbols:
                for tf in tfs:
                    try:
                        df = mt5.get_ohlc(symbol=sym, timeframe=tf, bars=5000)
                        if df is None or df.empty:
                            continue
                        try:
                            store.upsert(provider="mt5", symbol=sym, timeframe=tf, df=df)
                        except Exception:
                            pass
                        store.upsert(provider="csv", symbol=sym, timeframe=tf, df=df)
                        updated += 1
                    except Exception as e:
                        errors.append(f"{sym}:{tf}:{type(e).__name__}")
                        continue
        except Exception:
            errors.append("mt5_provider_unavailable")
    payload = {"provider": p, "updated": int(updated), "errors": errors, "tfs": list(tfs), "symbols": int(len(symbols))}
    _write_json(os.path.join(run_dir, "data_update.json"), payload)
    return payload


def cmd_scan(provider: str, run_dir: str, symbols: List[str], tfs: List[str], entry_mode: str, workers: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tf in tfs:
        rows = []
        loc = threading.local()

        def _scan_one(sym: str) -> Optional[Dict[str, Any]]:
            try:
                eng = getattr(loc, "eng", None)
                if eng is None:
                    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                    setattr(loc, "eng", eng)
                r, _ = run_multi_brain(engine=eng, symbol=sym, provider=str(provider), base_timeframe=tf, tranche="T1", include_debug=False)
                return r
            except Exception:
                return None

        items = symbols[: int(settings.MAX_SCAN_SYMBOLS)]
        w = int(max(1, int(workers)))
        if w <= 1:
            for sym in items:
                r = _scan_one(sym)
                if r:
                    rows.append(r)
        else:
            with ThreadPoolExecutor(max_workers=w) as pool:
                futs = [pool.submit(_scan_one, sym) for sym in items]
                for f in as_completed(futs):
                    r = f.result()
                    if r:
                        rows.append(r)
        rows.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
        p = os.path.join(run_dir, f"scan_{tf}.json")
        _write_json(p, rows)
        out[tf] = p
    return out


def cmd_backtest_top(
    provider: str,
    run_dir: str,
    scan_paths: Dict[str, str],
    top_n: int,
    tfs: List[str],
    entry_mode: str,
    workers: int,
    max_equity_drawdown_pct: float,
    free_cash_min_pct: float,
    risk_stop_policy: str,
    sizing_mode: str,
    risk_per_trade_pct: float,
    ai_risk_min_pct: float,
    ai_risk_max_pct: float,
    max_leverage: float,
) -> List[str]:
    out = []
    tasks: List[tuple[str, str]] = []
    for tf in tfs:
        sp = scan_paths.get(tf) or os.path.join(run_dir, f"scan_{tf}.json")
        scan_items = _read_json(sp, [])
        top_syms = pick_top_symbols(list(scan_items or []), top_n=int(top_n))
        for sym in top_syms:
            tasks.append((tf, sym))

    loc = threading.local()

    def _bt_one(tf: str, sym: str) -> Optional[tuple[str, str, Dict[str, Any]]]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            r = eng.backtest(
                symbol=sym,
                provider=str(provider),
                base_timeframe=tf,
                max_bars=5000,
                max_equity_drawdown_pct=float(max_equity_drawdown_pct),
                free_cash_min_pct=float(free_cash_min_pct),
                risk_stop_policy=str(risk_stop_policy),
                sizing_mode=str(sizing_mode),
                risk_per_trade_pct=float(risk_per_trade_pct),
                ai_assisted_sizing=True,
                ai_risk_min_pct=float(ai_risk_min_pct),
                ai_risk_max_pct=float(ai_risk_max_pct),
                max_leverage=float(max_leverage),
            )
            return (tf, sym, r)
        except Exception:
            return None

    w = int(max(1, int(workers)))
    if w <= 1:
        for tf, sym in tasks:
            res = _bt_one(tf, sym)
            if not res:
                continue
            tf2, sym2, r = res
            p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
            _write_json(p, r)
            out.append(p)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_bt_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                tf2, sym2, r = res
                p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
                _write_json(p, r)
                out.append(p)
    return out


def cmd_backtest_global(
    provider: str,
    run_dir: str,
    symbols: List[str],
    tfs: List[str],
    entry_mode: str,
    workers: int,
    max_equity_drawdown_pct: float,
    free_cash_min_pct: float,
    risk_stop_policy: str,
    sizing_mode: str,
    risk_per_trade_pct: float,
    ai_risk_min_pct: float,
    ai_risk_max_pct: float,
    max_leverage: float,
) -> List[str]:
    out = []
    tasks = [(tf, sym) for tf in tfs for sym in symbols]
    loc = threading.local()

    def _bt_one(tf: str, sym: str) -> Optional[tuple[str, str, Dict[str, Any]]]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            r = eng.backtest(
                symbol=sym,
                provider=str(provider),
                base_timeframe=tf,
                max_bars=5000,
                max_equity_drawdown_pct=float(max_equity_drawdown_pct),
                free_cash_min_pct=float(free_cash_min_pct),
                risk_stop_policy=str(risk_stop_policy),
                sizing_mode=str(sizing_mode),
                risk_per_trade_pct=float(risk_per_trade_pct),
                ai_assisted_sizing=True,
                ai_risk_min_pct=float(ai_risk_min_pct),
                ai_risk_max_pct=float(ai_risk_max_pct),
                max_leverage=float(max_leverage),
            )
            return (tf, sym, r)
        except Exception:
            return None

    w = int(max(1, int(workers)))
    if w <= 1:
        for tf, sym in tasks:
            res = _bt_one(tf, sym)
            if not res:
                continue
            tf2, sym2, r = res
            p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
            _write_json(p, r)
            out.append(p)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_bt_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                tf2, sym2, r = res
                p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
                _write_json(p, r)
                out.append(p)
    return out


def cmd_dataset_build(provider: str, symbols: List[str], tfs: List[str], entry_mode: str, workers: int) -> List[str]:
    out = []
    tasks = [(tf, sym) for tf in tfs for sym in symbols]
    loc = threading.local()

    def _ds_one(tf: str, sym: str) -> Optional[str]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            ds_path = os.path.join(str(settings.DATASETS_DIR), f"{sym}_{str(provider).lower()}_{tf}_ml.csv")
            r = build_trade_dataset(eng, symbol=sym, provider=str(provider), base_timeframe=tf, out_path=ds_path)
            if int(r.rows) > 0:
                return str(r.path)
            return None
        except Exception:
            return None

    w = int(max(1, int(workers)))
    if w <= 1:
        for tf, sym in tasks:
            p = _ds_one(tf, sym)
            if p:
                out.append(p)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_ds_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                p = f.result()
                if p:
                    out.append(p)
    return out


def cmd_report_setup_edge(run_dir: str, dataset_paths: List[str], backtest_paths: List[str]) -> Dict[str, str]:
    try:
        from scripts.analyze_runs import main as analyze_main

        argv = []
        for p in dataset_paths:
            argv += ["--dataset-csv", str(p)]
        for p in backtest_paths:
            argv += ["--backtest-json", str(p)]
        md = os.path.join(run_dir, "setup_edge.md")
        js = os.path.join(run_dir, "setup_edge.json")
        argv += ["--out-md", md, "--out-json", js]
        sys.argv = ["analyze_runs.py"] + argv
        analyze_main()
        return {"md": md, "json": js}
    except Exception:
        return {}


def cmd_train_stack(run_dir: str, dataset_paths: List[str]) -> Dict[str, Any]:
    if not dataset_paths:
        return {"error": "no datasets"}
    out_path = os.path.join(str(settings.MODELS_DIR), "naira_logreg_stack.json")
    feats = []
    try:
        from app.engine.dataset import FEATURES

        feats = list(FEATURES)
    except Exception:
        feats = []
    r = train_logreg_sgd_multi(dataset_csvs=list(dataset_paths), feature_names=feats, out_path=out_path, lr=0.15, epochs=200, l2=0.001, seed=7)
    payload = {"model_path": out_path, "rows": int(r.rows), "accuracy": float(r.accuracy), "feature_names": list(r.feature_names)}
    _write_json(os.path.join(run_dir, "train.json"), payload)
    return payload


def cmd_calibrate(run_dir: str, dataset_paths: List[str]) -> Dict[str, Any]:
    if not dataset_paths:
        return {"error": "no datasets"}
    out_path = os.path.join(str(settings.MODELS_DIR), "naira_logreg_stack.json")
    try:
        import pandas as pd

        dfs = []
        for p in dataset_paths:
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    dfs.append(df)
            except Exception:
                continue
        if not dfs:
            return {"error": "datasets vacíos"}
        df_all = pd.concat(dfs, ignore_index=True)
        tmp = os.path.join(run_dir, "calibration_dataset.csv")
        df_all.to_csv(tmp, index=False)
        rep = calibration_report(dataset_csv=tmp, model_path=out_path, bins=10)
        _write_json(os.path.join(run_dir, "calibration.json"), rep)
        return rep
    except Exception:
        return {"error": "calibration_failed"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tasks")
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in ("data:update", "scan", "backtest:top", "backtest:global", "dataset:build", "report:setup-edge", "train:stack", "train:calibrate", "all"):
        sub = sp.add_parser(name)
        sub.add_argument("--provider", required=True, choices=["binance", "mt5", "csv"])
        sub.add_argument("--entry-mode", default=os.getenv("PIPELINE_ENTRY_MODE", "hybrid"), choices=["hybrid", "pullback", "break_retest", "mean_reversion", "regime"])
        sub.add_argument("--workers", type=int, default=int(os.getenv("PIPELINE_WORKERS", "8") or "8"))
        sub.add_argument("--update-workers", type=int, default=int(os.getenv("PIPELINE_UPDATE_WORKERS", "2") or "2"))
        sub.add_argument("--max-equity-drawdown-pct", type=float, default=float(os.getenv("PIPELINE_MAX_DD_PCT", "50.0") or "50.0"))
        sub.add_argument("--free-cash-min-pct", type=float, default=float(os.getenv("PIPELINE_FREE_CASH_MIN_PCT", "0.20") or "0.20"))
        sub.add_argument(
            "--risk-stop-policy",
            default=os.getenv("PIPELINE_RISK_STOP_POLICY", "stop_immediate"),
            choices=["stop_immediate", "stop_no_new_trades", "stop_after_close"],
        )
        sub.add_argument("--sizing-mode", default=os.getenv("PIPELINE_SIZING_MODE", "ai_risk"), choices=["fixed_qty", "fixed_risk", "ai_risk"])
        sub.add_argument("--risk-per-trade-pct", type=float, default=float(os.getenv("PIPELINE_RISK_PCT", "2.0") or "2.0"))
        sub.add_argument("--ai-risk-min-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MIN_PCT", "1.0") or "1.0"))
        sub.add_argument("--ai-risk-max-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MAX_PCT", "5.0") or "5.0"))
        sub.add_argument("--max-leverage", type=float, default=float(os.getenv("PIPELINE_MAX_LEVERAGE", "1.0") or "1.0"))
    return p


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    provider = str(args.provider).lower()
    run_dir = make_run_dir(provider)
    run_tfs = list(RUN_TFS)
    ht_tfs = list(HT_TFS)
    update_tfs = run_tfs + ht_tfs
    symbols = load_symbols(provider)
    entry_mode = str(args.entry_mode)
    workers = int(args.workers)
    update_workers = int(args.update_workers)
    max_equity_drawdown_pct = float(args.max_equity_drawdown_pct)
    free_cash_min_pct = float(args.free_cash_min_pct)
    risk_stop_policy = str(args.risk_stop_policy)
    sizing_mode = str(args.sizing_mode)
    risk_per_trade_pct = float(args.risk_per_trade_pct)
    ai_risk_min_pct = float(args.ai_risk_min_pct)
    ai_risk_max_pct = float(args.ai_risk_max_pct)
    max_leverage = float(args.max_leverage)
    scan_paths: Dict[str, str] = {}
    backtests: List[str] = []
    datasets: List[str] = []
    if args.cmd == "data:update":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        return 0
    if args.cmd == "scan":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        return 0
    if args.cmd == "backtest:top":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
        )
        return 0
    if args.cmd == "backtest:global":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        cmd_backtest_global(
            provider,
            run_dir,
            symbols,
            run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
        )
        return 0
    if args.cmd == "dataset:build":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        cmd_dataset_build(provider, symbols, run_tfs, entry_mode, workers)
        return 0
    if args.cmd == "report:setup-edge":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
        )
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        cmd_report_setup_edge(run_dir, datasets, backtests)
        return 0
    if args.cmd == "train:stack":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": []})
        cmd_train_stack(run_dir, datasets)
        return 0
    if args.cmd == "train:calibrate":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": []})
        cmd_calibrate(run_dir, datasets)
        return 0
    if args.cmd == "all":
        print("updating data...")
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers)
        print("scanning...")
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        print("backtesting...")
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
        )
        print("building datasets...")
        datasets = cmd_dataset_build(
            provider,
            symbols=pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[:10],
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
        )
        print("writing datasets manifest...")
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        print("setting up report...")
        cmd_report_setup_edge(run_dir, datasets, backtests)
        print("training stack...")
        cmd_train_stack(run_dir, datasets)
        print("calibrating...")
        cmd_calibrate(run_dir, datasets)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
