from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass(frozen=True)
class WatchlistStore:
    path: str

    def load(self) -> List[str]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return []
        if raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            if isinstance(data, dict):
                items = data.get("symbols") or []
                return [str(x).strip() for x in items if str(x).strip()]
        return [s.strip() for s in raw.split(",") if s.strip()]

    def save(self, symbols: List[str]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        symbols_clean = [str(s).strip() for s in symbols if str(s).strip()]
        payload: Dict[str, Any] = {"symbols": symbols_clean}
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
