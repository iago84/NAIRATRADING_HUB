from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
import pandas as pd
import time


@dataclass(frozen=True)
class BinanceRestOHLCVProvider:
    base_url: str = "https://api.binance.com"

    def _fetch_klines(self, params: dict) -> list:
        url = f"{self.base_url}/api/v3/klines"
        last_err: Optional[Exception] = None
        for attempt in range(6):
            try:
                with httpx.Client(timeout=15.0) as c:
                    r = c.get(url, params=params)
                if r.status_code in (418, 429):
                    retry_after = r.headers.get("Retry-After")
                    sleep_s = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else (0.5 * (2**attempt))
                    time.sleep(min(10.0, sleep_s))
                    continue
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list):
                    return data
                return []
            except Exception as e:
                last_err = e
                time.sleep(min(10.0, 0.25 * (2**attempt)))
        if last_err is not None:
            raise last_err
        return []

    def get_ohlc(self, symbol: str, timeframe: str, limit: int = 1000, since_ms: Optional[int] = None) -> pd.DataFrame:
        sym = str(symbol).replace("/", "")
        params = {"symbol": sym, "interval": timeframe, "limit": int(limit)}
        if since_ms is not None:
            params["startTime"] = int(since_ms)
        data = self._fetch_klines(params)
        if not data:
            return pd.DataFrame()
        rows = []
        for k in data:
            rows.append(
                {
                    "datetime": pd.to_datetime(int(k[0]), unit="ms"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
            )
        return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])
