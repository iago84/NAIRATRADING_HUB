from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.core.config import settings
from app.engine.dataset import build_trade_dataset
from app.engine.history_store import HistoryStore
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.multi_brain import run_multi_brain
from scripts.tasks import cmd_data_update, RUN_TFS, HT_TFS
from scripts.pipeline_lib.log import info


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


def _read_watchlist(path: str, limit: int) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read() or "{}")
        items = obj.get("symbols") if isinstance(obj, dict) else obj
        out = [str(x).strip() for x in (items or []) if str(x).strip()]
        return out[: int(limit)]
    except Exception:
        return []


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")


def main() -> int:
    universe_size = 30
    try:
        v = int(os.getenv("PIPELINE_UNIVERSE", "30").strip() or "30")
        universe_size = 100 if v >= 100 else 30
    except Exception:
        universe_size = 30
    top_n = 10
    balance_usdt = 1000.0
    provider = "csv"
    tfs = list(RUN_TFS)
    update_tfs = list(RUN_TFS) + list(HT_TFS)
    wl = "crypto_top100.json" if universe_size >= 100 else "crypto_top30.json"
    wl_path = os.path.join(str(settings.DATA_DIR), "watchlists", wl)

    run_dir = os.path.join(str(settings.DATA_DIR), "reports", _utc_stamp(), f"run_{_run_stamp()}")
    os.makedirs(run_dir, exist_ok=True)
    info(f"run_pipeline start run_dir={run_dir}")

    symbols = _read_watchlist(wl_path, universe_size)
    if not symbols:
        raise SystemExit(f"watchlist vacía: {wl_path}")

    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi"))
    try:
        cmd_data_update("csv", run_dir, symbols, update_tfs)
    except Exception:
        pass

    all_datasets: List[str] = []
    all_backtests: List[str] = []

    for tf in tfs:
        info(f"scan tf={tf} symbols={min(len(symbols), int(settings.MAX_SCAN_SYMBOLS))}")
        scan_out = []
        for sym in symbols[: int(settings.MAX_SCAN_SYMBOLS)]:
            try:
                r, _ = run_multi_brain(engine=eng, symbol=sym, provider=provider, base_timeframe=tf, tranche="T1", include_debug=False)
                scan_out.append(r)
            except Exception:
                continue
        scan_out.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
        scan_path = os.path.join(run_dir, f"scan_{tf}.json")
        with open(scan_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(scan_out, ensure_ascii=False, indent=2))
        info(f"scan tf={tf} done items={len(scan_out)} out={scan_path}")

        top_syms = pick_top_symbols(scan_out, top_n=top_n)
        for sym in top_syms:
            try:
                r = eng.backtest(symbol=sym, provider="csv", base_timeframe=tf, max_bars=5000)
                bt_path = os.path.join(run_dir, f"backtest_{tf}_{sym}.json")
                with open(bt_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False))
                all_backtests.append(bt_path)
                info(f"backtest tf={tf} sym={sym} out={bt_path}")
            except Exception:
                continue
            try:
                ds_path = os.path.join(str(settings.DATASETS_DIR), f"{sym}_csv_{tf}_ml.csv")
                ds = build_trade_dataset(eng, symbol=sym, provider="csv", base_timeframe=tf, out_path=ds_path)
                if ds.rows > 0:
                    all_datasets.append(ds.path)
                    info(f"dataset tf={tf} sym={sym} rows={ds.rows} out={ds.path}")
            except Exception:
                continue

    man_path = os.path.join(run_dir, "datasets_manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"datasets": all_datasets, "backtests": all_backtests}, ensure_ascii=False, indent=2))

    try:
        from scripts.analyze_runs import main as analyze_main

        argv = []
        for p in all_datasets:
            argv += ["--dataset-csv", p]
        for p in all_backtests:
            argv += ["--backtest-json", p]
        argv += ["--out-md", os.path.join(run_dir, "setup_edge.md")]
        argv += ["--out-json", os.path.join(run_dir, "setup_edge.json")]
        sys.argv = ["analyze_runs.py"] + argv
        analyze_main()
    except Exception:
        pass
    info("run_pipeline done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
