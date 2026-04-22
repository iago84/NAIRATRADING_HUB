from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

import pandas as pd


AlligatorState = Literal["sleeping", "awakening", "trending", "unknown"]
AlligatorDirection = Literal["buy", "sell", "neutral"]


def smma(series: pd.Series, length: int) -> pd.Series:
    length = int(length)
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    alpha = 1.0 / float(length)
    out = []
    prev = float(series.iloc[0])
    out.append(prev)
    for v in series.iloc[1:]:
        prev = prev + alpha * (float(v) - prev)
        out.append(prev)
    return pd.Series(out, index=series.index)


def alligator_median(
    high: pd.Series,
    low: pd.Series,
    jaw: int = 13,
    teeth: int = 8,
    lips: int = 5,
    shift_jaw: int = 8,
    shift_teeth: int = 5,
    shift_lips: int = 3,
) -> pd.DataFrame:
    price_med = (high + low) / 2.0
    jaw_s = smma(price_med, jaw).shift(int(shift_jaw))
    teeth_s = smma(price_med, teeth).shift(int(shift_teeth))
    lips_s = smma(price_med, lips).shift(int(shift_lips))
    return pd.DataFrame({"jaw": jaw_s, "teeth": teeth_s, "lips": lips_s})


@dataclass(frozen=True)
class AlligatorSnapshot:
    direction: AlligatorDirection
    state: AlligatorState
    mouth: float


def classify_alligator(jaw: float, teeth: float, lips: float, atr: float | None = None) -> AlligatorSnapshot:
    if jaw is None or teeth is None or lips is None:
        return AlligatorSnapshot(direction="neutral", state="unknown", mouth=0.0)
    mouth_raw = abs(lips - teeth) + abs(teeth - jaw)
    denom = float(atr) if (atr is not None and atr > 0) else max(1e-9, abs(jaw))
    mouth = float(mouth_raw / denom)
    if mouth < 0.15:
        return AlligatorSnapshot(direction="neutral", state="sleeping", mouth=mouth)
    if lips > teeth > jaw:
        return AlligatorSnapshot(direction="buy", state="trending", mouth=mouth)
    if lips < teeth < jaw:
        return AlligatorSnapshot(direction="sell", state="trending", mouth=mouth)
    return AlligatorSnapshot(direction="neutral", state="awakening", mouth=mouth)


def latest_alligator(df: pd.DataFrame) -> Tuple[AlligatorSnapshot, pd.DataFrame]:
    if df is None or df.empty:
        return AlligatorSnapshot(direction="neutral", state="unknown", mouth=0.0), pd.DataFrame()
    a = alligator_median(df["high"], df["low"])
    merged = pd.concat([df.reset_index(drop=True), a.reset_index(drop=True)], axis=1)
    last = merged.iloc[-1]
    atr = float(last.get("atr")) if "atr" in merged.columns and pd.notna(last.get("atr")) else None
    snap = classify_alligator(float(last["jaw"]), float(last["teeth"]), float(last["lips"]), atr=atr)
    return snap, merged
