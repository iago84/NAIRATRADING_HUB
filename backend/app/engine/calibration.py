from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .model import load_model


@dataclass(frozen=True)
class CalibrationBin:
    lo: float
    hi: float
    n: int
    p_mean: float
    y_mean: float
    gap: float


@dataclass(frozen=True)
class CalibrationReport:
    bins: List[CalibrationBin]
    ece: float
    brier: float
    accuracy: float
    n: int


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2)) if len(p) else 0.0


def _ece(bins: List[CalibrationBin]) -> float:
    total = sum(int(b.n) for b in bins)
    if total <= 0:
        return 0.0
    return float(sum((b.n / total) * abs(b.gap) for b in bins))


def _reliability_bins(p: np.ndarray, y: np.ndarray, bins: int) -> Tuple[List[CalibrationBin], float, float, float, int]:
    n = int(len(p))
    pred = (p >= 0.5).astype(float)
    acc = float(np.mean(pred == y)) if n else 0.0
    brier = _brier(p, y)
    k = max(2, int(bins))
    edges = np.linspace(0.0, 1.0, num=k + 1)
    out_bins: List[CalibrationBin] = []
    for i in range(k):
        lo = float(edges[i])
        hi = float(edges[i + 1])
        if i == (k - 1):
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        idx = np.where(mask)[0]
        if len(idx) == 0:
            out_bins.append(CalibrationBin(lo=lo, hi=hi, n=0, p_mean=0.0, y_mean=0.0, gap=0.0))
            continue
        p_mean = float(np.mean(p[idx]))
        y_mean = float(np.mean(y[idx]))
        out_bins.append(CalibrationBin(lo=lo, hi=hi, n=int(len(idx)), p_mean=p_mean, y_mean=y_mean, gap=(p_mean - y_mean)))
    ece = _ece(out_bins)
    return out_bins, ece, brier, acc, n


def calibration_report(dataset_csv: str, model_path: str, bins: int = 10) -> Dict[str, Any]:
    df = pd.read_csv(dataset_csv)
    if df.empty:
        return {"error": "dataset vacío"}
    if "win" not in df.columns:
        return {"error": "dataset sin columna win"}
    y = df["win"].fillna(0.0).to_numpy(dtype=float)
    m = load_model(model_path)
    if m is None:
        return {"error": "modelo no encontrado"}
    probs = []
    for _, row in df.iterrows():
        feats = {k: float(row.get(k) or 0.0) for k in m.feature_names}
        probs.append(m.predict_proba(feats))
    p = np.asarray(probs, dtype=float)
    out_bins, ece, brier, acc, n = _reliability_bins(p, y, bins=int(bins))
    return {
        "n": n,
        "accuracy": acc,
        "brier": brier,
        "ece": ece,
        "bins": [b.__dict__ for b in out_bins],
    }


def calibration_report_by_regime(
    dataset_csv: str,
    model_path: str,
    bins: int = 10,
    regime_feature: str = "adx",
    cut1: float = 18.0,
    cut2: float = 25.0,
) -> Dict[str, Any]:
    df = pd.read_csv(dataset_csv)
    if df.empty:
        return {"error": "dataset vacío"}
    if "win" not in df.columns:
        return {"error": "dataset sin columna win"}
    if str(regime_feature) not in df.columns:
        return {"error": f"dataset sin columna {regime_feature}"}
    y = df["win"].fillna(0.0).to_numpy(dtype=float)
    reg = df[str(regime_feature)].fillna(0.0).to_numpy(dtype=float)
    m = load_model(model_path)
    if m is None:
        return {"error": "modelo no encontrado"}
    probs = []
    for _, row in df.iterrows():
        feats = {k: float(row.get(k) or 0.0) for k in m.feature_names}
        probs.append(m.predict_proba(feats))
    p = np.asarray(probs, dtype=float)

    masks = {
        f"{regime_feature}<={float(cut1):g}": reg <= float(cut1),
        f"{float(cut1):g}<{regime_feature}<={float(cut2):g}": (reg > float(cut1)) & (reg <= float(cut2)),
        f"{regime_feature}>{float(cut2):g}": reg > float(cut2),
    }
    out = {}
    for name, mask in masks.items():
        idx = np.where(mask)[0]
        if len(idx) == 0:
            out[name] = {"n": 0, "accuracy": 0.0, "brier": 0.0, "ece": 0.0, "bins": []}
            continue
        b, ece, brier, acc, n = _reliability_bins(p[idx], y[idx], bins=int(bins))
        out[name] = {"n": n, "accuracy": acc, "brier": brier, "ece": ece, "bins": [x.__dict__ for x in b]}
    return {"regime_feature": str(regime_feature), "cut1": float(cut1), "cut2": float(cut2), "reports": out}
