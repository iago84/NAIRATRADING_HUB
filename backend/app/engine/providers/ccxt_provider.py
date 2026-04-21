from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class CCXTOHLCVProvider:
    exchange_id: str = "binance"

    def _exchange(self):
        try:
            import ccxt
        except Exception as e:
            raise RuntimeError("ccxt no está instalado en este entorno") from e
        ex_cls = getattr(ccxt, self.exchange_id, None)
        if ex_cls is None:
            raise RuntimeError(f"exchange no soportado: {self.exchange_id}")
        return ex_cls({"enableRateLimit": True, "options": {"defaultType": "spot", "fetchMarkets": ["spot"]}})

    def get_ohlc(self, symbol: str, timeframe: str, limit: int = 500, since_ms: Optional[int] = None) -> pd.DataFrame:
        ex = self._exchange()
        ccxt_symbol = symbol.replace("USDT", "/USDT") if "USDT" in symbol and "/" not in symbol else symbol
        ohlcv = ex.fetch_ohlcv(ccxt_symbol, timeframe=timeframe, limit=int(limit), since=since_ms)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df[["datetime", "open", "high", "low", "close", "volume"]]
