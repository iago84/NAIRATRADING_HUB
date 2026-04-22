from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LogisticModel:
    feature_names: List[str]
    weights: List[float]
    bias: float

    def predict_proba(self, features: Dict[str, float]) -> float:
        x = np.array([float(features.get(k) or 0.0) for k in self.feature_names], dtype=float)
        w = np.array(self.weights, dtype=float)
        z = float(np.dot(w, x) + float(self.bias))
        z = max(-60.0, min(60.0, z))
        return float(1.0 / (1.0 + np.exp(-z)))


@dataclass(frozen=True)
class TrainResult:
    path: str
    rows: int
    accuracy: float
    feature_names: List[str]


def _standardize(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = np.mean(X, axis=0)
    sd = np.std(X, axis=0)
    sd = np.where(sd <= 1e-9, 1.0, sd)
    return (X - mu) / sd, mu, sd


def train_logreg_sgd(
    dataset_csv: str,
    feature_names: List[str],
    out_path: str,
    lr: float = 0.15,
    epochs: int = 200,
    l2: float = 0.001,
    seed: int = 7,
) -> TrainResult:
    df = pd.read_csv(dataset_csv)
    df = df.dropna(subset=["win"])
    if df.empty:
        raise RuntimeError("dataset vacío")
    X = df[feature_names].fillna(0.0).to_numpy(dtype=float)
    y = df["win"].to_numpy(dtype=float)
    Xs, mu, sd = _standardize(X)
    rnd = np.random.default_rng(int(seed))
    w = rnd.normal(0.0, 0.01, size=(Xs.shape[1],))
    b = 0.0
    for _ in range(int(epochs)):
        idx = rnd.permutation(len(Xs))
        for i in idx:
            xi = Xs[i]
            yi = float(y[i])
            z = float(np.dot(w, xi) + b)
            z = max(-60.0, min(60.0, z))
            p = 1.0 / (1.0 + np.exp(-z))
            grad = (p - yi)
            w = w - float(lr) * (grad * xi + float(l2) * w)
            b = b - float(lr) * grad
    logits = Xs @ w + b
    probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -60.0, 60.0)))
    preds = (probs >= 0.5).astype(float)
    acc = float(np.mean(preds == y))
    payload = {
        "feature_names": list(feature_names),
        "weights": (w / sd).tolist(),
        "bias": float(b - float(np.dot(w, mu / sd))),
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return TrainResult(path=out_path, rows=int(len(df)), accuracy=acc, feature_names=list(feature_names))


def train_logreg_sgd_multi(
    dataset_csvs: List[str],
    feature_names: List[str],
    out_path: str,
    lr: float = 0.15,
    epochs: int = 200,
    l2: float = 0.001,
    seed: int = 7,
) -> TrainResult:
    paths = [str(p) for p in (dataset_csvs or []) if str(p)]
    if not paths:
        raise RuntimeError("dataset_csvs vacío")
    dfs = []
    for p in paths:
        try:
            df = pd.read_csv(p)
            if not df.empty:
                dfs.append(df)
        except Exception:
            continue
    if not dfs:
        raise RuntimeError("no se pudieron leer datasets")
    df_all = pd.concat(dfs, ignore_index=True)
    tmp_path = out_path + ".tmp_dataset.csv"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_all.to_csv(tmp_path, index=False)
    return train_logreg_sgd(tmp_path, feature_names=feature_names, out_path=out_path, lr=lr, epochs=epochs, l2=l2, seed=seed)


def load_model(path: str) -> Optional[LogisticModel]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = json.loads(f.read())
    return LogisticModel(
        feature_names=list(payload.get("feature_names") or []),
        weights=list(payload.get("weights") or []),
        bias=float(payload.get("bias") or 0.0),
    )
