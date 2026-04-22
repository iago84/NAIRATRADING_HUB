import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.engine.history_store import HistoryStore
from app.engine.providers.binance_rest_provider import BinanceRestOHLCVProvider
from app.engine.providers.mt5_provider import MT5OHLCVProvider

import pandas as pd
from datetime import datetime, timedelta

from scripts.pipeline_lib.log import info, log


def normalize_timeframe(tf: str) -> str:
    s = str(tf).strip()
    if s.replace(".", "", 1).isdigit():
        return f"{int(float(s))}d"
    return s


def download_binance(store: HistoryStore, symbol: str, timeframe: str, years: int, limit: int) -> str:
    ex = BinanceRestOHLCVProvider()
    end = datetime.utcnow()
    start = end - timedelta(days=365 * max(1, int(years)))
    since = int(start.timestamp() * 1000)
    tf = normalize_timeframe(timeframe)
    chunks = []
    for _ in range(5000):
        df = ex.get_ohlc(symbol=symbol, timeframe=tf, limit=limit, since_ms=since)
        if df is None or df.empty:
            break
        chunks.append(df)
        last_dt = pd.to_datetime(df["datetime"].iloc[-1])
        since_next = int(last_dt.timestamp() * 1000) + 1
        if since_next <= since:
            break
        since = since_next
        if last_dt >= end:
            break
        if len(df) < limit:
            break
    df_all = pd.concat(chunks).drop_duplicates(subset=["datetime"]).sort_values("datetime") if chunks else pd.DataFrame()
    if df_all.empty:
        raise RuntimeError(f"No se pudo descargar histórico: {symbol} {tf}")
    return store.upsert(provider="binance", symbol=symbol, timeframe=tf, df=df_all)


def download_mt5(store: HistoryStore, symbol: str, timeframe: str, years: int) -> str:
    mt5 = MT5OHLCVProvider()
    end = datetime.utcnow()
    start = end - timedelta(days=365 * max(1, int(years)))
    df = mt5.get_ohlc_range(symbol=symbol, timeframe=timeframe, start_ts=int(start.timestamp()), end_ts=int(end.timestamp()))
    if df is None or df.empty:
        raise RuntimeError(f"No se pudo descargar histórico: {symbol} {timeframe}")
    return store.upsert(provider="mt5", symbol=symbol, timeframe=timeframe, df=df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["binance", "mt5"])
    ap.add_argument("--symbols", required=True, help="Lista separada por comas")
    ap.add_argument("--timeframes", required=True, help="Lista separada por comas (ej: 1h,4h,1d)")
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    store = HistoryStore(base_dir=settings.DATA_DIR)
    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    tfs = [normalize_timeframe(t) for t in str(args.timeframes).split(",") if str(t).strip()]
    out = []
    info(f"bulk_download provider={args.provider} symbols={len(symbols)} tfs={','.join(tfs)} years={args.years}")
    for sym in symbols:
        for tf in tfs:
            log(f"bulk_download sym={sym} tf={tf}", verbose=True)
            if args.provider == "binance":
                path = download_binance(store, sym, tf, years=args.years, limit=args.limit)
            else:
                path = download_mt5(store, sym, tf, years=args.years)
            out.append({"symbol": sym, "timeframe": tf, "path": path})
            print(path)
    print(out)
    info(f"bulk_download done items={len(out)}")


if __name__ == "__main__":
    main()
