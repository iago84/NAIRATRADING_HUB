import argparse
from datetime import datetime, timedelta
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.engine.history_store import HistoryStore
from app.engine.providers.binance_rest_provider import BinanceRestOHLCVProvider
from app.engine.providers.mt5_provider import MT5OHLCVProvider


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["binance", "mt5"])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--timeframe", required=True)
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    store = HistoryStore(base_dir=settings.DATA_DIR)
    provider = args.provider
    symbol = args.symbol
    timeframe = str(args.timeframe).strip()
    if timeframe.replace(".", "", 1).isdigit():
        timeframe = f"{int(float(timeframe))}d"
    years = max(1, int(args.years))

    end = datetime.utcnow()
    start = end - timedelta(days=365 * years)

    if provider == "binance":
        tf = timeframe
        ex = BinanceRestOHLCVProvider()
        since = int(start.timestamp() * 1000)
        chunks = []
        for _ in range(2000):
            df = ex.get_ohlc(symbol=symbol, timeframe=tf, limit=args.limit, since_ms=since)
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
            if len(df) < args.limit:
                break
        df_all = pd.concat(chunks).drop_duplicates(subset=["datetime"]).sort_values("datetime") if chunks else pd.DataFrame()
        if df_all.empty:
            raise RuntimeError("No se pudo descargar histórico (binance)")
        path = store.upsert(provider="binance", symbol=symbol, timeframe=tf, df=df_all)
        print(path)
        return

    mt5 = MT5OHLCVProvider()
    df = mt5.get_ohlc_range(symbol=symbol, timeframe=timeframe, start_ts=int(start.timestamp()), end_ts=int(end.timestamp()))
    if df is None or df.empty:
        raise RuntimeError("No se pudo descargar histórico (mt5)")
    path = store.upsert(provider="mt5", symbol=symbol, timeframe=timeframe, df=df)
    print(path)


if __name__ == "__main__":
    main()
