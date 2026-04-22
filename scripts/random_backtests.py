import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.history_store import HistoryStore

from scripts.pipeline_lib.log import info, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["binance", "mt5", "csv"])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--years_back", type=int, default=3)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--min_days", type=int, default=30)
    ap.add_argument("--max_days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rnd = random.Random(int(args.seed))
    store = HistoryStore(base_dir=settings.DATA_DIR)
    provider = str(args.provider)
    symbol = str(args.symbol)
    tf = str(args.timeframe)
    df = store.load(provider=provider, symbol=symbol, timeframe=tf) if provider != "csv" else pd.DataFrame()
    if df.empty and provider == "csv":
        raise RuntimeError("provider=csv requiere usar histórico en data/history/csv o usar provider binance/mt5")
    if df.empty:
        raise RuntimeError("No hay histórico local. Descarga primero con scripts/bulk_download.py o scripts/download_history.py")

    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    end_all = df["datetime"].iloc[-1]
    start_all = end_all - timedelta(days=int(365 * max(1, args.years_back)))
    df = df[df["datetime"] >= start_all].reset_index(drop=True)
    if df.empty:
        raise RuntimeError("No hay datos en el rango de years_back")

    out_path = args.out or os.path.join(settings.DATASETS_DIR, "random_backtests", f"{symbol}_{provider}_{tf}.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(entry_mode="none"))
    results = []
    info(f"random_backtests start provider={provider} symbol={symbol} tf={tf} runs={args.runs} out={out_path}")
    for i in range(int(args.runs)):
        dur_days = rnd.randint(int(args.min_days), int(args.max_days))
        dur = timedelta(days=dur_days)
        start_min = df["datetime"].iloc[0]
        start_max = df["datetime"].iloc[-1] - dur
        if start_max <= start_min:
            break
        span_sec = int((start_max - start_min).total_seconds())
        offset_sec = rnd.randint(0, max(1, span_sec))
        start = start_min + timedelta(seconds=offset_sec)
        end = start + dur
        w = df[(df["datetime"] >= start) & (df["datetime"] <= end)].copy()
        if len(w) < 200:
            continue
        tmp_csv = os.path.join(settings.DATASETS_DIR, "random_backtests", "tmp", f"{symbol}_{provider}_{tf}_{i}.csv")
        os.makedirs(os.path.dirname(tmp_csv), exist_ok=True)
        w.to_csv(tmp_csv, index=False)
        r = eng.backtest(symbol=symbol, provider="csv", base_timeframe=tf, csv_path=tmp_csv, max_bars=None, feature_mode="fast")
        metrics = r.get("metrics") or {}
        row = {"run": i, "symbol": symbol, "provider": provider, "timeframe": tf, "start": start.isoformat(), "end": end.isoformat(), "metrics": metrics}
        results.append(row)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(row)
        log(f"random_backtests run={i} metrics={metrics}", verbose=bool(os.getenv("PIPELINE_VERBOSE", "")))

    print({"out": out_path, "runs": len(results)})
    info(f"random_backtests done runs={len(results)} out={out_path}")


if __name__ == "__main__":
    main()
