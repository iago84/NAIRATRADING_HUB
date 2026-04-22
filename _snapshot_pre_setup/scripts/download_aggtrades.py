import argparse
import csv
import time
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="Ej: BTCUSDT")
    ap.add_argument("--start", required=True, help="ISO UTC: 2024-01-01T00:00:00Z")
    ap.add_argument("--end", required=True, help="ISO UTC: 2024-01-02T00:00:00Z")
    ap.add_argument("--out", required=True, help="CSV output")
    ap.add_argument("--compare_ohlc_csv", default="", help="CSV OHLC (1m) para comparar contra aggTrades")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--base_url", default="https://api.binance.com")
    args = ap.parse_args()

    symbol = str(args.symbol).replace("/", "").upper()
    start = datetime.fromisoformat(str(args.start).replace("Z", "+00:00")).astimezone(timezone.utc)
    end = datetime.fromisoformat(str(args.end).replace("Z", "+00:00")).astimezone(timezone.utc)
    if end <= start:
        raise SystemExit("end must be > start")

    out_path = str(args.out)
    start_ms = _ms(start)
    end_ms = _ms(end)
    limit = max(1, min(1000, int(args.limit)))

    url = f"{str(args.base_url).rstrip('/')}/api/v3/aggTrades"
    total = 0
    last_ts = start_ms

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "timestamp_ms", "price", "qty", "is_buyer_maker", "trade_id"])
        with httpx.Client(timeout=20.0) as c:
            for _ in range(2000000):
                if last_ts >= end_ms:
                    break
                params = {"symbol": symbol, "startTime": int(last_ts), "endTime": int(end_ms), "limit": int(limit)}
                r = c.get(url, params=params)
                if r.status_code in (418, 429):
                    time.sleep(1.0)
                    continue
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list) or len(data) == 0:
                    break
                for row in data:
                    ts = int(row.get("T") or 0)
                    if ts <= 0:
                        continue
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
                    w.writerow([dt, ts, row.get("p"), row.get("q"), bool(row.get("m")), int(row.get("a") or 0)])
                    total += 1
                    last_ts = max(last_ts, ts + 1)
                if len(data) < limit:
                    break

    print(out_path)
    print({"symbol": symbol, "rows": total, "start": start.isoformat(), "end": end.isoformat()})
    cmp_path = str(args.compare_ohlc_csv or "").strip()
    if cmp_path:
        df_t = pd.read_csv(out_path)
        df_t["datetime"] = pd.to_datetime(df_t["datetime"], utc=True, errors="coerce")
        df_t = df_t.dropna(subset=["datetime"])
        df_t["price"] = pd.to_numeric(df_t["price"], errors="coerce")
        df_t["qty"] = pd.to_numeric(df_t["qty"], errors="coerce").fillna(0.0)
        df_t = df_t.dropna(subset=["price"])
        df_t["minute"] = df_t["datetime"].dt.floor("min")
        g = df_t.sort_values("datetime").groupby("minute", as_index=False)
        ohlc_t = g.agg(open=("price", "first"), high=("price", "max"), low=("price", "min"), close=("price", "last"), volume=("qty", "sum"))
        ohlc_t.rename(columns={"minute": "datetime"}, inplace=True)
        df_o = pd.read_csv(cmp_path)
        df_o["datetime"] = pd.to_datetime(df_o["datetime"], utc=True, errors="coerce")
        df_o = df_o.dropna(subset=["datetime"])
        for c in ("open", "high", "low", "close"):
            df_o[c] = pd.to_numeric(df_o[c], errors="coerce")
        df = ohlc_t.merge(df_o[["datetime", "open", "high", "low", "close"]], on="datetime", how="inner", suffixes=("_agg", "_ohlc"))
        if df.empty:
            print({"compare": "no_overlap"})
            return
        mae_close = float((df["close_agg"] - df["close_ohlc"]).abs().mean())
        mae_high = float((df["high_agg"] - df["high_ohlc"]).abs().mean())
        mae_low = float((df["low_agg"] - df["low_ohlc"]).abs().mean())
        print({"compare": {"rows_overlap": int(len(df)), "mae_close": mae_close, "mae_high": mae_high, "mae_low": mae_low}})


if __name__ == "__main__":
    main()
