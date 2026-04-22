from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


TIMEFRAME_MAP = {
    "1m": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
    "1d": "TIMEFRAME_D1",
    "1w": "TIMEFRAME_W1",
}


@dataclass(frozen=True)
class MT5OHLCVProvider:
    def _mt5(self):
        try:
            import MetaTrader5 as mt5
        except Exception as e:
            raise RuntimeError("MetaTrader5 no está instalado en este entorno") from e
        if not mt5.initialize():
            raise RuntimeError("No se pudo inicializar MT5 (terminal no disponible o sin permisos)")
        return mt5

    def get_ohlc(self, symbol: str, timeframe: str, bars: int = 500) -> pd.DataFrame:
        mt5 = self._mt5()
        key = TIMEFRAME_MAP.get(timeframe)
        if not key:
            raise ValueError("timeframe no soportado")
        tf = getattr(mt5, key)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, int(bars))
        df = pd.DataFrame(rates)
        if df.empty:
            return pd.DataFrame()
        df["datetime"] = pd.to_datetime(df["time"], unit="s")
        if "tick_volume" in df.columns and "volume" not in df.columns:
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def get_ohlc_range(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> pd.DataFrame:
        mt5 = self._mt5()
        key = TIMEFRAME_MAP.get(timeframe)
        if not key:
            raise ValueError("timeframe no soportado")
        tf = getattr(mt5, key)
        rates = mt5.copy_rates_range(symbol, tf, int(start_ts), int(end_ts))
        df = pd.DataFrame(rates)
        if df.empty:
            return pd.DataFrame()
        df["datetime"] = pd.to_datetime(df["time"], unit="s")
        if "tick_volume" in df.columns and "volume" not in df.columns:
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["datetime", "open", "high", "low", "close", "volume"]]
