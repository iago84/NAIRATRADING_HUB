from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from ..ohlc import normalize_ohlcv
from ..history_store import HistoryStore


@dataclass(frozen=True)
class CsvProvider:
    base_dir: str

    def resolve_path(self, symbol: str, timeframe: str) -> str:
        safe_sym = symbol.replace("/", "").replace("\\", "").replace(":", "")
        return os.path.join(self.base_dir, "history", "csv", safe_sym, f"{timeframe}.csv")

    def load(self, symbol: str, timeframe: str, path: Optional[str] = None) -> pd.DataFrame:
        p = path or self.resolve_path(symbol, timeframe)
        if not os.path.exists(p):
            return pd.DataFrame()
        df = pd.read_csv(p)
        return normalize_ohlcv(df)

    def store(self) -> HistoryStore:
        return HistoryStore(base_dir=self.base_dir)
