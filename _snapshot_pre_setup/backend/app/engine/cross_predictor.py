from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from .indicators import ema as ema_series
from .ohlc import normalize_ohlcv


@dataclass(frozen=True)
class CrossPredictConfig:
    fast_ema: int = 25
    slow_ema: int = 80
    seq_len: int = 64
    horizon_bars: int = 96
    adx_gate: float = 0.0
    epochs: int = 8
    lr: float = 1e-3
    batch_size: int = 128
    dropout: float = 0.15
    seed: int = 7


class CrossLSTMClassifier(nn.Module):
    def __init__(self, n_features: int, hidden: int = 64, layers: int = 1, dropout: float = 0.15):
        super().__init__()
        self.lstm = nn.LSTM(input_size=n_features, hidden_size=hidden, num_layers=layers, batch_first=True, dropout=float(dropout) if layers > 1 else 0.0)
        self.drop = nn.Dropout(float(dropout))
        self.fc = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        last = self.drop(last)
        return self.fc(last).squeeze(-1)


def _set_seed(seed: int) -> None:
    torch.manual_seed(int(seed))
    np.random.seed(int(seed))


def _ema_cross_series(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    d = normalize_ohlcv(df)
    if d.empty:
        return d
    c = pd.to_numeric(d["close"], errors="coerce").to_numpy(dtype=float)
    ef = ema_series(pd.Series(c), int(fast)).to_numpy(dtype=float)
    es = ema_series(pd.Series(c), int(slow)).to_numpy(dtype=float)
    delta = ef - es
    out = d.copy()
    out["ema_fast"] = ef
    out["ema_slow"] = es
    out["delta"] = delta
    out["delta_slope"] = pd.Series(delta).diff().fillna(0.0).to_numpy(dtype=float)
    out["delta_abs"] = np.abs(delta)
    return out


def _labels_cross_within(delta: np.ndarray, horizon: int) -> np.ndarray:
    y = np.zeros(len(delta), dtype=float)
    s = np.sign(delta)
    for i in range(len(delta) - int(horizon) - 1):
        base = s[i]
        if base == 0:
            base = s[i - 1] if i > 0 else 0.0
        if base == 0:
            continue
        nxt = s[i + 1 : i + 1 + int(horizon)]
        if np.any(nxt == 0):
            y[i] = 1.0
        elif np.any(nxt * base < 0):
            y[i] = 1.0
    return y


def build_cross_dataset(df: pd.DataFrame, cfg: CrossPredictConfig) -> Dict[str, Any]:
    d = _ema_cross_series(df, fast=int(cfg.fast_ema), slow=int(cfg.slow_ema))
    if d.empty or len(d) < int(cfg.seq_len + cfg.horizon_bars + 10):
        return {"error": "insufficient_data", "rows": int(len(d))}
    delta = pd.to_numeric(d["delta"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    slope = pd.to_numeric(d["delta_slope"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    close = pd.to_numeric(d["close"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    atr = np.maximum(1e-9, pd.to_numeric(d.get("atr"), errors="coerce").fillna(0.0).to_numpy(dtype=float))
    atr_pct = (atr / np.maximum(1e-9, close)) * 100.0
    y = _labels_cross_within(delta, horizon=int(cfg.horizon_bars))
    feats = np.stack([delta / atr, slope / np.maximum(1e-9, atr), atr_pct], axis=1)
    seq = int(cfg.seq_len)
    X = []
    Y = []
    T = []
    for i in range(seq, len(feats) - int(cfg.horizon_bars) - 1):
        X.append(feats[i - seq : i])
        Y.append(y[i])
        T.append(pd.to_datetime(d["datetime"].iloc[i]).isoformat())
    Xn = np.asarray(X, dtype=float)
    Yn = np.asarray(Y, dtype=float)
    mu = np.mean(Xn.reshape(-1, Xn.shape[-1]), axis=0)
    sd = np.std(Xn.reshape(-1, Xn.shape[-1]), axis=0)
    sd = np.where(sd <= 1e-9, 1.0, sd)
    Xs = (Xn - mu) / sd
    return {"X": Xs, "y": Yn, "timestamps": T, "mu": mu, "sd": sd, "rows": int(len(Yn))}


def train_cross_lstm(df: pd.DataFrame, cfg: CrossPredictConfig) -> Dict[str, Any]:
    _set_seed(int(cfg.seed))
    pack = build_cross_dataset(df, cfg)
    if "error" in pack:
        return pack
    X = pack["X"]
    y = pack["y"]
    mu = pack["mu"]
    sd = pack["sd"]
    n = int(len(y))
    if n < 500:
        return {"error": "insufficient_samples", "rows": n}
    split = int(n * 0.8)
    Xtr = torch.tensor(X[:split], dtype=torch.float32)
    ytr = torch.tensor(y[:split], dtype=torch.float32)
    Xva = torch.tensor(X[split:], dtype=torch.float32)
    yva = torch.tensor(y[split:], dtype=torch.float32)
    model = CrossLSTMClassifier(n_features=int(X.shape[-1]), hidden=64, layers=1, dropout=float(cfg.dropout))
    opt = torch.optim.Adam(model.parameters(), lr=float(cfg.lr))
    loss_fn = nn.BCEWithLogitsLoss()
    bs = int(cfg.batch_size)
    for _ in range(int(cfg.epochs)):
        model.train()
        idx = torch.randperm(Xtr.shape[0])
        for j in range(0, Xtr.shape[0], bs):
            b = idx[j : j + bs]
            xb = Xtr[b]
            yb = ytr[b]
            opt.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            opt.step()
    model.eval()
    with torch.no_grad():
        p = torch.sigmoid(model(Xva)).cpu().numpy()
    pred = (p >= 0.5).astype(float)
    acc = float(np.mean(pred == y[split:])) if len(pred) else 0.0
    return {"model": model, "mu": mu, "sd": sd, "rows": int(n), "accuracy": acc}


def save_cross_model(path: str, cfg: CrossPredictConfig, model: CrossLSTMClassifier, mu: np.ndarray, sd: np.ndarray) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "cfg": cfg.__dict__,
        "state_dict": model.state_dict(),
        "mu": mu.tolist(),
        "sd": sd.tolist(),
    }
    torch.save(payload, path)
    meta_path = path + ".json"
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"cfg": cfg.__dict__}, ensure_ascii=False, indent=2))
    return path


def load_cross_model(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    payload = torch.load(path, map_location="cpu")
    cfg_d = payload.get("cfg") or {}
    cfg = CrossPredictConfig(**cfg_d)
    mu = np.asarray(payload.get("mu") or [], dtype=float)
    sd = np.asarray(payload.get("sd") or [], dtype=float)
    model = CrossLSTMClassifier(n_features=int(len(mu)), hidden=64, layers=1, dropout=float(cfg.dropout))
    model.load_state_dict(payload.get("state_dict") or {})
    model.eval()
    return {"cfg": cfg, "model": model, "mu": mu, "sd": sd}


def predict_cross(
    df: pd.DataFrame,
    cfg: CrossPredictConfig,
    model_bundle: Optional[Dict[str, Any]] = None,
    mc_samples: int = 32,
) -> Dict[str, Any]:
    d = _ema_cross_series(df, fast=int(cfg.fast_ema), slow=int(cfg.slow_ema))
    if d.empty or len(d) < int(cfg.seq_len + 5):
        return {"error": "insufficient_data", "rows": int(len(d))}
    last_dt = pd.to_datetime(d["datetime"].iloc[-1]).isoformat()
    delta = float(d["delta"].iloc[-1])
    slope = float(d["delta_slope"].iloc[-1])
    close = float(d["close"].iloc[-1])
    atr = float(d.get("atr").iloc[-1]) if "atr" in d.columns and pd.notna(d.get("atr").iloc[-1]) else 0.0
    atr = float(max(1e-9, atr))
    atr_pct = float((atr / max(1e-9, close)) * 100.0)
    bars_to_cross = None
    ci = None
    try:
        w = max(30, int(cfg.seq_len))
        seg = pd.to_numeric(d["delta"].iloc[-w:], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        x = np.arange(len(seg), dtype=float)
        a, b = np.polyfit(x, seg, 1)
        if abs(a) > 1e-12:
            k = int(np.ceil((-seg[-1]) / a))
            if 0 <= k <= int(cfg.horizon_bars):
                bars_to_cross = int(k)
        resid = seg - (a * x + b)
        s = float(np.std(resid))
        if abs(a) > 1e-12:
            k_mean = (-seg[-1]) / a
            k_lo = (-seg[-1] - 1.96 * s) / a
            k_hi = (-seg[-1] + 1.96 * s) / a
            ci = {"bars_lo": float(min(k_lo, k_hi)), "bars_hi": float(max(k_lo, k_hi)), "resid_std": float(s)}
    except Exception:
        pass

    prob_cross = None
    prob_ci = None
    if model_bundle is not None:
        mb_cfg = model_bundle.get("cfg")
        model = model_bundle.get("model")
        mu = model_bundle.get("mu")
        sd = model_bundle.get("sd")
        if model is not None and mu is not None and sd is not None and len(mu) == 3:
            seq = int(mb_cfg.seq_len) if mb_cfg is not None else int(cfg.seq_len)
            if len(d) >= seq:
                delta_s = pd.to_numeric(d["delta"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                slope_s = pd.to_numeric(d["delta_slope"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                close_s = pd.to_numeric(d["close"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
                atr_s = np.maximum(1e-9, pd.to_numeric(d.get("atr"), errors="coerce").fillna(0.0).to_numpy(dtype=float))
                atr_pct_s = (atr_s / np.maximum(1e-9, close_s)) * 100.0
                feats = np.stack([delta_s / atr_s, slope_s / atr_s, atr_pct_s], axis=1)
                x = feats[-seq:]
                x = (x - mu) / np.where(sd <= 1e-9, 1.0, sd)
                xt = torch.tensor(x[None, :, :], dtype=torch.float32)
                model.train()
                ps = []
                for _ in range(int(max(1, mc_samples))):
                    with torch.no_grad():
                        p = float(torch.sigmoid(model(xt)).cpu().numpy().reshape(-1)[0])
                    ps.append(p)
                model.eval()
                prob_cross = float(np.mean(ps))
                prob_ci = {"p05": float(np.percentile(ps, 5)), "p95": float(np.percentile(ps, 95)), "n": int(len(ps))}

    return {
        "asof": last_dt,
        "fast_ema": int(cfg.fast_ema),
        "slow_ema": int(cfg.slow_ema),
        "delta": float(delta),
        "delta_slope": float(slope),
        "atr_pct": float(atr_pct),
        "bars_to_cross_est": bars_to_cross,
        "bars_to_cross_ci": ci,
        "prob_cross_within_horizon": prob_cross,
        "prob_ci": prob_ci,
        "horizon_bars": int(cfg.horizon_bars),
    }


def backtest_cross_predictions(df: pd.DataFrame, cfg: CrossPredictConfig, folds: int = 4) -> Dict[str, Any]:
    d = _ema_cross_series(df, fast=int(cfg.fast_ema), slow=int(cfg.slow_ema))
    if d.empty or len(d) < int(cfg.seq_len + cfg.horizon_bars + 200):
        return {"error": "insufficient_data", "rows": int(len(d))}
    pack = build_cross_dataset(d, cfg)
    if "error" in pack:
        return pack
    X = pack["X"]
    y = pack["y"]
    n = int(len(y))
    segs = max(3, int(folds))
    step = n // segs
    out = []
    for i in range(segs - 1):
        a0 = i * step
        a1 = (i + 1) * step
        b0 = a1
        b1 = n if (i + 2) >= segs else (i + 2) * step
        Xtr = torch.tensor(X[a0:a1], dtype=torch.float32)
        ytr = torch.tensor(y[a0:a1], dtype=torch.float32)
        Xte = torch.tensor(X[b0:b1], dtype=torch.float32)
        yte = y[b0:b1]
        if len(ytr) < 500 or len(yte) < 200:
            continue
        _set_seed(int(cfg.seed) + i)
        model = CrossLSTMClassifier(n_features=int(X.shape[-1]), hidden=64, layers=1, dropout=float(cfg.dropout))
        opt = torch.optim.Adam(model.parameters(), lr=float(cfg.lr))
        loss_fn = nn.BCEWithLogitsLoss()
        bs = int(cfg.batch_size)
        for _ in range(int(cfg.epochs)):
            model.train()
            idx = torch.randperm(Xtr.shape[0])
            for j in range(0, Xtr.shape[0], bs):
                b = idx[j : j + bs]
                xb = Xtr[b]
                yb = ytr[b]
                opt.zero_grad()
                logits = model(xb)
                loss = loss_fn(logits, yb)
                loss.backward()
                opt.step()
        model.eval()
        with torch.no_grad():
            p = torch.sigmoid(model(Xte)).cpu().numpy()
        pred = (p >= 0.5).astype(float)
        acc = float(np.mean(pred == yte)) if len(yte) else 0.0
        brier = float(np.mean((p - yte) ** 2)) if len(yte) else 0.0
        out.append({"fold": i, "test_n": int(len(yte)), "accuracy": acc, "brier": brier})
    return {"fast_ema": int(cfg.fast_ema), "slow_ema": int(cfg.slow_ema), "horizon_bars": int(cfg.horizon_bars), "folds": out}
