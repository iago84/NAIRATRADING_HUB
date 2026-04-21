from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal, List

from ..core.config import settings

Asset = Literal["crypto", "fx", "metals"]
Tranche = Literal["T0", "T1", "T2", "T3"]


def tranche_for_balance(asset: Asset, balance: float) -> Tranche:
    b = float(balance or 0.0)
    if asset == "crypto":
        if b < float(settings.CRYPTO_T0_MAX):
            return "T0"
        if b < float(settings.CRYPTO_T1_MAX):
            return "T1"
        if b < float(settings.CRYPTO_T2_MAX):
            return "T2"
        return "T3"
    if asset in ("fx", "metals"):
        if b < float(settings.FX_T0_MAX):
            return "T0"
        if b < float(settings.FX_T1_MAX):
            return "T1"
        if b < float(settings.FX_T2_MAX):
            return "T2"
        return "T3"
    return "T0"


@dataclass(frozen=True)
class UniverseManager:
    data_dir: str

    def _wl_path(self, name: str) -> str:
        return os.path.join(self.data_dir, "watchlists", name)

    def _load(self, name: str) -> List[str]:
        p = self._wl_path(name)
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            arr = json.loads(f.read())
        return [str(x).strip() for x in (arr or []) if str(x).strip()]

    def symbols(self, asset: Asset, tranche: Tranche) -> List[str]:
        if asset == "crypto":
            if tranche == "T0":
                return self._load("crypto_top2.json")
            if tranche == "T1":
                return self._load("crypto_top10.json")
            if tranche == "T2":
                return self._load("crypto_top30.json")
            return self._load("crypto_top100.json")
        if asset == "fx":
            if tranche == "T0":
                return self._load("fx_micro.json")
            if tranche == "T1":
                return self._load("fx_majors.json")
            return self._load("fx_majors_minors.json")
        if asset == "metals":
            return self._load("metals.json")
        return []
