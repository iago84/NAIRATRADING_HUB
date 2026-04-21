from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .ohlc import normalize_ohlcv


@dataclass(frozen=True)
class HistoryStore:
    base_dir: str

    def resolve_path(self, provider: str, symbol: str, timeframe: str) -> str:
        safe_sym = symbol.replace("/", "").replace("\\", "").replace(":", "")
        return os.path.join(self.base_dir, "history", provider.lower(), safe_sym, f"{timeframe}.csv")

    def load(self, provider: str, symbol: str, timeframe: str) -> pd.DataFrame:
        path = self.resolve_path(provider, symbol, timeframe)
        if not os.path.exists(path):
            return pd.DataFrame()
        return normalize_ohlcv(pd.read_csv(path))

    def upsert(self, provider: str, symbol: str, timeframe: str, df: pd.DataFrame) -> str:
        df = normalize_ohlcv(df)
        path = self.resolve_path(provider, symbol, timeframe)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            prev = normalize_ohlcv(pd.read_csv(path))
            merged = pd.concat([prev, df]).drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
            merged.to_csv(path, index=False)
        else:
            df.to_csv(path, index=False)
        return path

    def latest_datetime(self, provider: str, symbol: str, timeframe: str) -> Optional[pd.Timestamp]:
        df = self.load(provider, symbol, timeframe)
        if df.empty:
            return None
        return pd.to_datetime(df["datetime"].iloc[-1])
