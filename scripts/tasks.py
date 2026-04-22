from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.core.config import settings
from app.engine.calibration import calibration_report
from app.engine.dataset import build_trade_dataset
from app.engine.model import train_logreg_sgd_multi
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.multi_brain import run_multi_brain


DEFAULT_TFS = ["5m", "15m", "1h", "4h", "1d"]


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


def cmd_scan(provider: str, run_dir: str, symbols: List[str], tfs: List[str]) -> Dict[str, str]:
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi"))
    out: Dict[str, str] = {}
    for tf in tfs:
        rows = []
        for sym in symbols[: int(settings.MAX_SCAN_SYMBOLS)]:
            try:
                r, _ = run_multi_brain(engine=eng, symbol=sym, provider=str(provider), base_timeframe=tf, tranche="T1", include_debug=False)
                rows.append(r)
            except Exception:
                continue
        rows.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
        p = os.path.join(run_dir, f"scan_{tf}.json")
        _write_json(p, rows)
        out[tf] = p
    return out


def cmd_backtest_top(provider: str, run_dir: str, scan_paths: Dict[str, str], top_n: int, tfs: List[str]) -> List[str]:
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi"))
    out = []
    for tf in tfs:
        sp = scan_paths.get(tf) or os.path.join(run_dir, f"scan_{tf}.json")
        scan_items = _read_json(sp, [])
        top_syms = pick_top_symbols(list(scan_items or []), top_n=int(top_n))
        for sym in top_syms:
            try:
                r = eng.backtest(symbol=sym, provider=str(provider), base_timeframe=tf, max_bars=5000)
                p = os.path.join(run_dir, f"backtest_{tf}_{sym}.json")
                _write_json(p, r)
                out.append(p)
            except Exception:
                continue
    return out


def cmd_dataset_build(provider: str, symbols: List[str], tfs: List[str]) -> List[str]:
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi"))
    out = []
    for tf in tfs:
        for sym in symbols:
            try:
                ds_path = os.path.join(str(settings.DATASETS_DIR), f"{sym}_{str(provider).lower()}_{tf}_ml.csv")
                r = build_trade_dataset(eng, symbol=sym, provider=str(provider), base_timeframe=tf, out_path=ds_path)
                if int(r.rows) > 0:
                    out.append(r.path)
            except Exception:
                continue
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
    return p


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    provider = str(args.provider).lower()
    run_dir = make_run_dir(provider)
    tfs = list(DEFAULT_TFS)
    symbols = load_symbols(provider)
    scan_paths: Dict[str, str] = {}
    backtests: List[str] = []
    datasets: List[str] = []
    if args.cmd == "data:update":
        _write_json(os.path.join(run_dir, "data_update.json"), {"provider": provider, "status": "noop"})
        return 0
    if args.cmd == "scan":
        cmd_scan(provider, run_dir, symbols, tfs)
        return 0
    if args.cmd == "backtest:top":
        scan_paths = cmd_scan(provider, run_dir, symbols, tfs)
        cmd_backtest_top(provider, run_dir, scan_paths, top_n=_top_n(), tfs=tfs)
        return 0
    if args.cmd == "dataset:build":
        cmd_dataset_build(provider, symbols, tfs)
        return 0
    if args.cmd == "report:setup-edge":
        return 0
    if args.cmd == "train:stack":
        return 0
    if args.cmd == "train:calibrate":
        return 0
    if args.cmd == "all":
        scan_paths = cmd_scan(provider, run_dir, symbols, tfs)
        backtests = cmd_backtest_top(provider, run_dir, scan_paths, top_n=_top_n(), tfs=tfs)
        datasets = cmd_dataset_build(provider, symbols=pick_top_symbols(_read_json(scan_paths.get("1h", ""), []), _top_n()) or symbols[:10], tfs=["1h"])
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        cmd_report_setup_edge(run_dir, datasets, backtests)
        cmd_train_stack(run_dir, datasets)
        cmd_calibrate(run_dir, datasets)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

