from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple, cast

import numpy as np
import pandas as pd

from .indicators import adx as adx_series
from .indicators import atr as atr_series
from .indicators import ema as ema_series
from .ohlc import TF_TO_PANDAS_RULE, normalize_ohlcv, resample_ohlcv
from .providers import CsvProvider, CCXTOHLCVProvider, MT5OHLCVProvider
from .levels import build_levels, confluence_score, pivot_points_prev_day, fractals, latest_fractal_levels, fibo_horizontal, fibo_vertical_timezones, fibo_confluence_score, nearest_levels_summary
from .alligator import latest_alligator
from .regression import rolling_linreg_slope_pct, linreg_metrics
from .entry_rules import decide_entry
from .execution_gates import confluence_gate, execution_threshold_gate, structural_gate, timing_gate
from .risk_stops import RiskStopConfig, RiskStopPolicy, apply_risk_stop
from .timing import trend_age_bars_from_directions
from .setup_classifier import classify_setups
from .filters import OperationalFilterConfig, apply_operational_filters
from ..core.logger import get_logger
from ..core.config import settings
from ..core.metrics import metrics_singleton


Direction = Literal["buy", "sell", "neutral"]

_TF_SECONDS: Dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def _valid_until_iso(ts_iso: str, timeframe: str, ttl_bars: int) -> Optional[str]:
    try:
        dt = pd.to_datetime(ts_iso, utc=True)
        sec = int(_TF_SECONDS.get(str(timeframe), 0))
        if sec <= 0:
            return None
        out = dt + timedelta(seconds=int(sec) * int(ttl_bars))
        return out.isoformat()
    except Exception:
        return None


@dataclass(frozen=True)
class NairaConfig:
    ema_periods: Tuple[int, ...] = (3, 5, 10, 25, 80, 180, 220, 550, 1000)
    slope_window_bars: int = 12
    alignment_threshold: float = 0.7
    slope_threshold_pct: float = 0.02
    adx_length: int = 14
    adx_threshold: float = 18.0
    regression_window_bars: int = 50
    atr_length: int = 14
    tp_atr_mult: float = 2.0
    sl_atr_mult: float = 1.2
    min_confidence: float = 0.55
    strategy_mode: str = "single"
    entry_mode: str = "hybrid"
    entry_tol_atr: float = 0.6
    trend_age_min_bars: int = 0
    trend_age_max_bars: int = 240
    ema_compression_max: float = 6.0
    require_rejection: bool = False
    min_wick_ratio: float = 1.2
    ai_entry_threshold: float = 0.0
    ensemble_w_conf: float = 0.65
    ensemble_w_ai: float = 0.35
    ensemble_w_alignment: float = 0.05
    ensemble_w_slope: float = 0.05
    ensemble_w_adx: float = 0.03
    partial_1r_pct: float = 0.5
    partial_2r_pct: float = 0.25
    trailing_atr_mult: float = 1.4
    structure_trailing: bool = False
    structure_trailing_lookback: int = 2
    soft_close_adx_drop: float = 14.0
    time_stop_bars: int = 0
    time_stop_min_r: float = 0.0
    pyramiding_enabled: bool = False
    pyramid_add_r: float = 0.8
    pyramid_add_pct: float = 0.5
    pyramid_max_adds: int = 2
    pyramid_lot_series: Tuple[float, ...] = (1.0, 3.0, 1.0, 1.0)
    anti_martingale_mult: float = 1.5
    anti_martingale_max_steps: int = 3
    vol_target_atr_pct: float = 1.2
    kelly_fraction: float = 0.25
    max_risk_pct: float = 2.0
    portfolio_max_corr: float = 0.85
    portfolio_corr_lookback: int = 200
    portfolio_global_cooldown_bars: int = 0
    portfolio_max_majors: int = 1
    portfolio_max_alts: int = 3
    confirm_higher_tfs: bool = True
    timing_timeframe: str = "15m"
    timing_min_confidence: float = 0.5
    use_structure_exits: bool = True
    structure_sl_buffer_atr: float = 0.10
    structure_tp_buffer_atr: float = 0.10
    invalidate_on_4h_flip: bool = True
    invalidate_on_adx_ema_loss: bool = True
    cache_ttl_seconds: float = 30.0
    cache_max_items: int = 64
    tf_weights: Tuple[Tuple[str, float], ...] = (
        ("1w", 5.0),
        ("1d", 4.0),
        ("4h", 3.0),
        ("1h", 2.0),
        ("30m", 1.0),
        ("15m", 0.8),
        ("5m", 0.5),
        ("1m", 0.25),
    )


class NairaEngine:
    def __init__(self, data_dir: str, config: Optional[NairaConfig] = None):
        self.config = config or NairaConfig()
        self.csv = CsvProvider(base_dir=data_dir)
        self.ccxt = CCXTOHLCVProvider(exchange_id="binance")
        self.mt5 = MT5OHLCVProvider()
        self.logger = get_logger("naira_engine")
        self._model = None
        self._ohlc_cache: Dict[str, Tuple[float, pd.DataFrame]] = {}
        self._ohlc_cache_order: List[str] = []
        self._redis = None
        redis_url = str(os.getenv("REDIS_URL") or "").strip()
        if redis_url:
            try:
                import redis

                self._redis = redis.from_url(redis_url)
            except Exception:
                self._redis = None

    def _cache_key(self, provider: str, symbol: str, timeframe: str, csv_path: Optional[str]) -> str:
        return f"{str(provider).lower()}|{str(symbol)}|{str(timeframe)}|{str(csv_path) if csv_path else ''}"

    def _cache_get(self, key: str) -> Optional[pd.DataFrame]:
        try:
            v = self._ohlc_cache.get(key)
            if not v:
                if self._redis is not None:
                    try:
                        raw = self._redis.get(key)
                        if raw:
                            df = pd.read_json(raw.decode("utf-8"), orient="split")
                            df = normalize_ohlcv(df)
                            self._cache_set(key, df)
                            return df
                    except Exception:
                        return None
                return None
            ts, df = v
            if (datetime.utcnow().timestamp() - float(ts)) > float(self.config.cache_ttl_seconds):
                self._ohlc_cache.pop(key, None)
                return None
            if key in self._ohlc_cache_order:
                self._ohlc_cache_order.remove(key)
            self._ohlc_cache_order.append(key)
            return df
        except Exception:
            return None

    def _cache_set(self, key: str, df: pd.DataFrame) -> None:
        try:
            self._ohlc_cache[key] = (datetime.utcnow().timestamp(), df)
            if key in self._ohlc_cache_order:
                self._ohlc_cache_order.remove(key)
            self._ohlc_cache_order.append(key)
            if self._redis is not None:
                try:
                    ttl = max(1, int(float(self.config.cache_ttl_seconds)))
                    payload = df.tail(6000).to_json(orient="split", date_format="iso")
                    self._redis.setex(key, ttl, payload)
                except Exception:
                    pass
            lim = int(self.config.cache_max_items)
            while lim > 0 and len(self._ohlc_cache_order) > lim:
                old = self._ohlc_cache_order.pop(0)
                self._ohlc_cache.pop(old, None)
        except Exception:
            return

    def load_model(self, path: str):
        try:
            from .model import load_model

            self._model = load_model(path)
        except Exception:
            self._model = None

    def score_ai(self, features: Dict[str, float]) -> Optional[float]:
        if self._model is None:
            return None
        try:
            return float(self._model.predict_proba(features))
        except Exception:
            return None

    def load_ohlc(self, symbol: str, timeframe: str, provider: str, csv_path: Optional[str] = None) -> pd.DataFrame:
        p = str(provider or "csv").lower()
        key = self._cache_key(provider=p, symbol=symbol, timeframe=timeframe, csv_path=csv_path)
        cached = self._cache_get(key)
        if cached is not None and not cached.empty:
            return cached
        if p == "csv":
            df = self.csv.load(symbol=symbol, timeframe=timeframe, path=csv_path)
            df_n = normalize_ohlcv(df)
            self._cache_set(key, df_n)
            return df_n
        if p in ("binance", "ccxt"):
            store = self.csv.store()
            local_path = store.resolve_path(provider="binance", symbol=symbol, timeframe=timeframe)
            if os.path.exists(local_path):
                df_n = store.load(provider="binance", symbol=symbol, timeframe=timeframe)
                self._cache_set(key, df_n)
                return df_n
            df = self.ccxt.get_ohlc(symbol=symbol, timeframe=timeframe, limit=1000)
            try:
                store.upsert(provider="binance", symbol=symbol, timeframe=timeframe, df=df)
            except Exception:
                pass
            df_n = normalize_ohlcv(df)
            self._cache_set(key, df_n)
            return df_n
        if p == "mt5":
            store = self.csv.store()
            local_path = store.resolve_path(provider="mt5", symbol=symbol, timeframe=timeframe)
            if os.path.exists(local_path):
                df_n = store.load(provider="mt5", symbol=symbol, timeframe=timeframe)
                self._cache_set(key, df_n)
                return df_n
            df = self.mt5.get_ohlc(symbol=symbol, timeframe=timeframe, bars=2000)
            try:
                store.upsert(provider="mt5", symbol=symbol, timeframe=timeframe, df=df)
            except Exception:
                pass
            df_n = normalize_ohlcv(df)
            self._cache_set(key, df_n)
            return df_n
        raise ValueError("provider no soportado")

    def _apply_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = normalize_ohlcv(df)
        if df.empty:
            return df
        out = df.copy()
        close = out["close"]
        for p in self.config.ema_periods:
            out[f"ema_{p}"] = ema_series(close, length=int(p))
        out["adx"] = adx_series(out["high"], out["low"], out["close"], length=int(self.config.adx_length))
        out["atr"] = atr_series(out["high"], out["low"], out["close"], length=int(self.config.atr_length))
        return out

    def _alignment(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        periods = list(self.config.ema_periods)
        pairs: List[Tuple[str, str]] = []
        for i in range(len(periods) - 1):
            a = f"ema_{periods[i]}"
            b = f"ema_{periods[i + 1]}"
            if a in df.columns and b in df.columns:
                pairs.append((a, b))
        if not pairs:
            nan = pd.Series([np.nan] * len(df), index=df.index)
            return nan, nan
        bull_parts = []
        bear_parts = []
        valid_parts = []
        for a, b in pairs:
            valid = df[a].notna() & df[b].notna()
            bull_parts.append(((df[a] > df[b]) & valid).astype(float))
            bear_parts.append(((df[a] < df[b]) & valid).astype(float))
            valid_parts.append(valid.astype(float))
        valid_sum = pd.concat(valid_parts, axis=1).sum(axis=1).replace(0, np.nan)
        bull = pd.concat(bull_parts, axis=1).sum(axis=1) / valid_sum
        bear = pd.concat(bear_parts, axis=1).sum(axis=1) / valid_sum
        return bull, bear

    def _slope_score(self, df: pd.DataFrame) -> pd.Series:
        w = int(self.config.slope_window_bars)
        fast = [p for p in (3, 5, 10, 25) if f"ema_{p}" in df.columns]
        if not fast:
            return pd.Series([np.nan] * len(df), index=df.index)
        parts = []
        for p in fast:
            s = df[f"ema_{p}"]
            prev = s.shift(w).replace(0, np.nan)
            parts.append(((s - prev) / prev) * 100.0)
        return pd.concat(parts, axis=1).mean(axis=1)

    def frame_state(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        df = self._apply_features(df)
        if df.empty:
            return pd.DataFrame()
        bull, bear = self._alignment(df)
        slope = self._slope_score(df)
        adx = df["adx"]
        atr = df["atr"]
        reg_slope_pct, reg_r2 = rolling_linreg_slope_pct(df["close"].to_numpy(dtype=float), window=int(self.config.regression_window_bars))
        reg_slope_pct_s = pd.Series(reg_slope_pct, index=df.index)
        reg_r2_s = pd.Series(reg_r2, index=df.index)
        close = df["close"].replace(0, np.nan)
        ema_spread_fast_pct = pd.Series([np.nan] * len(df), index=df.index)
        ema_spread_trend_pct = pd.Series([np.nan] * len(df), index=df.index)
        ema_compression = pd.Series([np.nan] * len(df), index=df.index)
        if "ema_3" in df.columns and "ema_25" in df.columns:
            ema_spread_fast_pct = ((df["ema_3"] - df["ema_25"]) / close) * 100.0
        if "ema_25" in df.columns and "ema_220" in df.columns:
            ema_spread_trend_pct = ((df["ema_25"] - df["ema_220"]) / close) * 100.0
        if all(c in df.columns for c in ("ema_3", "ema_25", "ema_80", "ema_220")):
            comp = (df["ema_3"] - df["ema_25"]).abs() + (df["ema_25"] - df["ema_80"]).abs() + (df["ema_80"] - df["ema_220"]).abs()
            ema_compression = (comp / close) * 100.0

        z_win = max(10, int(self.config.regression_window_bars))
        slope_mean = slope.rolling(z_win, min_periods=10).mean()
        slope_std = slope.rolling(z_win, min_periods=10).std().replace(0, np.nan)
        slope_z = (slope - slope_mean) / slope_std
        curvature = slope - slope.shift(max(2, int(self.config.slope_window_bars)))

        fast_periods = [p for p in (3, 5, 10, 25) if f"ema_{p}" in df.columns]
        slopes_fast = []
        for p in fast_periods:
            s = df[f"ema_{p}"]
            prev = s.shift(int(self.config.slope_window_bars)).replace(0, np.nan)
            slopes_fast.append(((s - prev) / prev) * 100.0)
        if slopes_fast:
            mat = pd.concat(slopes_fast, axis=1)
            pos = (mat > 0).mean(axis=1)
            neg = (mat < 0).mean(axis=1)
            slope_alignment = pos.where(pos >= neg, neg)
            slope_parallelism = mat.std(axis=1)
        else:
            slope_alignment = pd.Series([np.nan] * len(df), index=df.index)
            slope_parallelism = pd.Series([np.nan] * len(df), index=df.index)

        bull_ok = (bull >= float(self.config.alignment_threshold)) & (slope >= float(self.config.slope_threshold_pct)) & (adx >= float(self.config.adx_threshold))
        bear_ok = (bear >= float(self.config.alignment_threshold)) & (slope <= -float(self.config.slope_threshold_pct)) & (adx >= float(self.config.adx_threshold))

        direction = pd.Series(["neutral"] * len(df), index=df.index)
        direction[bull_ok] = "buy"
        direction[bear_ok] = "sell"

        conf = pd.Series([0.0] * len(df), index=df.index, dtype=float)
        conf = conf + bull.fillna(0.0).where(direction == "buy", 0.0) * 0.55
        conf = conf + bear.fillna(0.0).where(direction == "sell", 0.0) * 0.55
        conf = conf + slope.abs().fillna(0.0).clip(0, 1.0) * 0.25
        conf = conf + (adx.fillna(0.0) / 50.0).clip(0, 1.0) * 0.20
        conf = conf + reg_r2_s.fillna(0.0).clip(0, 1.0) * 0.05
        conf = conf + reg_slope_pct_s.abs().fillna(0.0).clip(0, 1.0) * 0.05
        conf = conf + slope_alignment.fillna(0.0).clip(0, 1.0) * 0.03
        conf = conf + slope_z.abs().fillna(0.0).clip(0, 2.0) * 0.01
        conf = conf.clip(0, 1.0)

        out = pd.DataFrame(
            {
                "datetime": df["datetime"],
                "timeframe": timeframe,
                "direction": direction,
                "confidence": conf,
                "alignment_bull": bull,
                "alignment_bear": bear,
                "alignment": bull.where(direction == "buy", bear.where(direction == "sell", (bull.fillna(0) + bear.fillna(0)) / 2.0)),
                "slope_score": slope,
                "regression_slope_pct": reg_slope_pct_s,
                "regression_r2": reg_r2_s,
                "slope_z": slope_z,
                "curvature": curvature,
                "slope_alignment": slope_alignment,
                "slope_parallelism": slope_parallelism,
                "ema_spread_fast_pct": ema_spread_fast_pct,
                "ema_spread_trend_pct": ema_spread_trend_pct,
                "ema_compression": ema_compression,
                "adx": adx,
                "atr": atr,
                "close": df["close"],
            }
        )
        return out.dropna(subset=["datetime", "close"]).reset_index(drop=True)

    def _vote(self, states: Dict[str, Dict[str, Any]]) -> Tuple[Direction, float, float]:
        weights = dict(self.config.tf_weights)
        bull = 0.0
        bear = 0.0
        total_w = 0.0
        conf_w = 0.0
        for tf, st in states.items():
            if st.get("valid") is False:
                continue
            w = float(weights.get(tf, 0.0))
            if w <= 0:
                continue
            total_w += w
            d = st.get("direction", "neutral")
            c = float(st.get("confidence", 0.0))
            conf_w += w * c
            if d == "buy":
                bull += w * c
            elif d == "sell":
                bear += w * c
        if total_w <= 0:
            return "neutral", 0.0, 0.0
        conf = conf_w / total_w
        strength = max(bull, bear)
        if bull > bear * 1.05 and bull >= float(self.config.min_confidence):
            return "buy", conf, strength
        if bear > bull * 1.05 and bear >= float(self.config.min_confidence):
            return "sell", conf, strength
        return "neutral", conf, strength

    def analyze(
        self,
        symbol: str,
        provider: str,
        base_timeframe: str,
        csv_path: Optional[str] = None,
        timeframes: Optional[List[str]] = None,
        include_debug: bool = False,
    ) -> Dict[str, Any]:
        metrics_singleton.rolling["signals_10m"].add()
        tfs = timeframes or ["1w", "1d", "4h", base_timeframe]
        tfs = [tf for tf in tfs if tf in TF_TO_PANDAS_RULE]
        if "4h" not in tfs:
            tfs.insert(0, "4h")
        if base_timeframe not in tfs:
            tfs.append(base_timeframe)

        df_base = self.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider, csv_path=csv_path)
        df_base = normalize_ohlcv(df_base)
        if df_base.empty:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "provider": provider,
                "base_timeframe": base_timeframe,
                "direction": "neutral",
                "confidence": 0.0,
                "opportunity_score": 0.0,
                "price": 0.0,
                "frames": [],
                "reasons": ["Sin datos (CSV no encontrado o vacío)"],
                "risk": {"entry_price": 0.0},
            }

        base_sec = int(_TF_SECONDS.get(str(base_timeframe), 0))
        states_latest: Dict[str, Dict[str, Any]] = {}
        frames_out: List[Dict[str, Any]] = []
        price = 0.0
        ts = datetime.utcnow().isoformat()
        base_features: Optional[pd.DataFrame] = None
        base_atr: Optional[float] = None
        df_feat_base = self._apply_features(df_base)
        for tf in tfs:
            rule = TF_TO_PANDAS_RULE[tf]
            tf_sec = int(_TF_SECONDS.get(str(tf), 0))
            if tf == base_timeframe:
                df_tf = df_base
            elif tf_sec > 0 and base_sec > 0 and tf_sec > base_sec:
                df_tf = resample_ohlcv(df_base, rule=rule)
            else:
                if str(provider).lower() == "csv":
                    continue
                df_tf = self.load_ohlc(symbol=symbol, timeframe=tf, provider=provider, csv_path=None)
                df_tf = normalize_ohlcv(df_tf)
            st_df = self.frame_state(df_tf, timeframe=tf)
            if st_df.empty:
                continue
            if tf == base_timeframe:
                base_features = st_df
            last = st_df.iloc[-1]
            trend_age_bars = 0
            if tf == base_timeframe:
                try:
                    dirs = [str(x) for x in st_df["direction"].to_list()][-300:]
                    trend_age_bars = int(trend_age_bars_from_directions(dirs))
                except Exception:
                    trend_age_bars = 0
            if tf == base_timeframe:
                price = float(last["close"])
                ts = pd.to_datetime(last["datetime"]).isoformat()
                base_atr = float(last.get("atr")) if pd.notna(last.get("atr")) else None
            st = {
                "timeframe": tf,
                "direction": str(last["direction"]),
                "confidence": float(last["confidence"]),
                "trend_age_bars": int(trend_age_bars) if tf == base_timeframe else None,
                "alignment": float(last.get("alignment") or 0.0),
                "slope_score": float(last.get("slope_score")) if pd.notna(last.get("slope_score")) else float("nan"),
                "regression_slope_pct": float(last.get("regression_slope_pct")) if pd.notna(last.get("regression_slope_pct")) else float("nan"),
                "regression_r2": float(last.get("regression_r2")) if pd.notna(last.get("regression_r2")) else float("nan"),
                "slope_z": float(last.get("slope_z")) if pd.notna(last.get("slope_z")) else float("nan"),
                "curvature": float(last.get("curvature")) if pd.notna(last.get("curvature")) else float("nan"),
                "slope_alignment": float(last.get("slope_alignment")) if pd.notna(last.get("slope_alignment")) else float("nan"),
                "slope_parallelism": float(last.get("slope_parallelism")) if pd.notna(last.get("slope_parallelism")) else float("nan"),
                "ema_spread_fast_pct": float(last.get("ema_spread_fast_pct")) if pd.notna(last.get("ema_spread_fast_pct")) else float("nan"),
                "ema_spread_trend_pct": float(last.get("ema_spread_trend_pct")) if pd.notna(last.get("ema_spread_trend_pct")) else float("nan"),
                "ema_compression": float(last.get("ema_compression")) if pd.notna(last.get("ema_compression")) else float("nan"),
                "adx": float(last.get("adx")) if pd.notna(last.get("adx")) else None,
                "atr": float(last.get("atr")) if pd.notna(last.get("atr")) else None,
            }
            try:
                adx_v = float(st.get("adx") or 0.0)
                st["adx_score"] = float(np.clip(adx_v / 50.0, 0.0, 1.0))
            except Exception:
                st["adx_score"] = 0.0
            try:
                atr_v = float(st.get("atr") or 0.0)
                close_v = float(last.get("close") or 0.0)
                atr_pct = (atr_v / close_v) * 100.0 if (close_v > 0 and atr_v > 0) else 0.0
                st["atr_pct"] = float(atr_pct)
                mn = float(settings.MIN_ATR_PCT)
                mx = float(settings.MAX_ATR_PCT)
                pen = 0.0
                if mn > 0 and atr_pct < mn:
                    pen = float(np.clip((mn - atr_pct) / mn, 0.0, 1.0))
                elif mx > 0 and atr_pct > mx:
                    pen = float(np.clip((atr_pct - mx) / mx, 0.0, 1.0))
                st["volatility_penalty"] = float(pen)
            except Exception:
                st["atr_pct"] = 0.0
                st["volatility_penalty"] = 0.0
            try:
                piv_tf = pivot_points_prev_day(df_tf.iloc[-5000:] if len(df_tf) > 5000 else df_tf)
                lv_tf = build_levels(df_tf.iloc[-2000:] if len(df_tf) > 2000 else df_tf, atr=st.get("atr"), lookback=3)
                st["level_confluence_score"] = float(confluence_score(price=float(last.get("close") or 0.0), pivots=piv_tf, levels=lv_tf, atr=st.get("atr")))
            except Exception:
                st["level_confluence_score"] = 0.0
            st["valid"] = bool(pd.notna(last.get("slope_score")) and pd.notna(last.get("alignment")) and pd.notna(last.get("regression_r2")))
            states_latest[tf] = st
            st_public = dict(st)
            st_public.pop("valid", None)
            if st_public.get("trend_age_bars") is None:
                st_public.pop("trend_age_bars", None)
            try:
                if not np.isfinite(float(st_public.get("slope_score"))):
                    st_public["slope_score"] = 0.0
            except Exception:
                st_public["slope_score"] = 0.0
            try:
                if not np.isfinite(float(st_public.get("regression_slope_pct"))):
                    st_public["regression_slope_pct"] = 0.0
            except Exception:
                st_public["regression_slope_pct"] = 0.0
            try:
                if not np.isfinite(float(st_public.get("regression_r2"))):
                    st_public["regression_r2"] = 0.0
            except Exception:
                st_public["regression_r2"] = 0.0
            for k in (
                "slope_z",
                "curvature",
                "slope_alignment",
                "slope_parallelism",
                "ema_spread_fast_pct",
                "ema_spread_trend_pct",
                "ema_compression",
            ):
                try:
                    if not np.isfinite(float(st_public.get(k))):
                        st_public[k] = 0.0
                except Exception:
                    st_public[k] = 0.0
            frames_out.append(st_public)

        g_dir, g_conf, strength = self._vote(states_latest)
        reasons: List[str] = []
        if g_dir == "neutral":
            reasons.append("Sin confluencia suficiente multi-timeframe")
        else:
            reasons.append(f"Dirección multi-timeframe: {g_dir}")
        if "4h" in states_latest:
            reasons.append(f"4h {states_latest['4h'].get('direction')} conf={states_latest['4h'].get('confidence'):.2f}")

        piv = pivot_points_prev_day(df_base)
        lv = build_levels(df_base, atr=base_atr, lookback=3)
        conf_lv = confluence_score(price=price, pivots=piv, levels=lv, atr=base_atr)
        if conf_lv >= 0.35:
            reasons.append(f"Confluencia niveles/pivots: {conf_lv:.2f}")
        lvl_summary = nearest_levels_summary(df_base, clustered=lv, price=price, atr=base_atr)
        if lvl_summary.get("nearest_support_touches", 0) >= 3 or lvl_summary.get("nearest_resistance_touches", 0) >= 3:
            reasons.append("Nivel relevante (touches)")
        try:
            if base_atr and base_atr > 0 and not df_feat_base.empty and "4h" in states_latest:
                ema25 = float(df_feat_base["ema_25"].iloc[-1]) if "ema_25" in df_feat_base.columns and pd.notna(df_feat_base["ema_25"].iloc[-1]) else None
                ema80 = float(df_feat_base["ema_80"].iloc[-1]) if "ema_80" in df_feat_base.columns and pd.notna(df_feat_base["ema_80"].iloc[-1]) else None
                near_support = float(lvl_summary.get("nearest_support_distance_atr") or 0.0) <= 0.9
                near_res = float(lvl_summary.get("nearest_resistance_distance_atr") or 0.0) <= 0.9
                ema_ok = False
                if ema25 is not None:
                    ema_ok = (abs(float(price) - ema25) / float(base_atr)) <= 0.9
                if not ema_ok and ema80 is not None:
                    ema_ok = (abs(float(price) - ema80) / float(base_atr)) <= 0.9
                h4_dir = str(states_latest["4h"].get("direction") or "neutral")
                if g_dir == "buy" and h4_dir == "buy" and near_support and ema_ok:
                    reasons.append("Nivel cercano + EMA clave + 4h alineado")
                elif g_dir == "sell" and h4_dir == "sell" and near_res and ema_ok:
                    reasons.append("Nivel cercano + EMA clave + 4h alineado")
        except Exception:
            pass

        fr = latest_fractal_levels(df_base, lookback=2)
        fib_h = fibo_horizontal(df_base, lookback=120)
        fib_t = fibo_vertical_timezones(df_base, lookback=2)
        conf_fib = fibo_confluence_score(price=price, fibo=fib_h, atr=base_atr)
        if conf_fib >= 0.1:
            reasons.append(f"Confluencia Fibonacci: {conf_fib:.2f}")

        ali_snap, _ = latest_alligator(self._apply_features(df_base))
        if ali_snap.state != "unknown":
            reasons.append(f"Alligator {ali_snap.state} dir={ali_snap.direction} mouth={ali_snap.mouth:.2f}")

        atr = None
        if base_timeframe in states_latest:
            atr = states_latest[base_timeframe].get("atr")
        sl = None
        tp = None
        safe_exit_hint = None
        if atr and price:
            if g_dir == "buy":
                sl = price - float(self.config.sl_atr_mult) * float(atr)
                tp = price + float(self.config.tp_atr_mult) * float(atr)
            elif g_dir == "sell":
                sl = price + float(self.config.sl_atr_mult) * float(atr)
                tp = price - float(self.config.tp_atr_mult) * float(atr)
            safe_exit_hint = "A 1R: mover SL a BE; parciales en niveles; cerrar si 4h pierde confluencia"
            if bool(self.config.use_structure_exits) and base_atr and base_atr > 0:
                try:
                    buf_sl = float(self.config.structure_sl_buffer_atr) * float(base_atr)
                    buf_tp = float(self.config.structure_tp_buffer_atr) * float(base_atr)
                    if g_dir == "buy":
                        ns = lvl_summary.get("nearest_support")
                        nr = lvl_summary.get("nearest_resistance")
                        if ns is not None:
                            sl_lv = float(ns) - float(buf_sl)
                            if sl_lv < float(price):
                                sl = float(min(float(sl), sl_lv)) if sl is not None else float(sl_lv)
                        if nr is not None:
                            tp_lv = float(nr) - float(buf_tp)
                            if tp_lv > float(price):
                                tp = float(min(float(tp), tp_lv)) if tp is not None else float(tp_lv)
                        pv_r1 = piv.get("R1")
                        if pv_r1 is not None and float(pv_r1) > float(price):
                            tp = float(min(float(tp), float(pv_r1) - float(buf_tp))) if tp is not None else float(float(pv_r1) - float(buf_tp))
                    elif g_dir == "sell":
                        ns = lvl_summary.get("nearest_support")
                        nr = lvl_summary.get("nearest_resistance")
                        if nr is not None:
                            sl_lv = float(nr) + float(buf_sl)
                            if sl_lv > float(price):
                                sl = float(max(float(sl), sl_lv)) if sl is not None else float(sl_lv)
                        if ns is not None:
                            tp_lv = float(ns) + float(buf_tp)
                            if tp_lv < float(price):
                                tp = float(max(float(tp), tp_lv)) if tp is not None else float(tp_lv)
                        pv_s1 = piv.get("S1")
                        if pv_s1 is not None and float(pv_s1) < float(price):
                            tp = float(max(float(tp), float(pv_s1) + float(buf_tp))) if tp is not None else float(float(pv_s1) + float(buf_tp))
                except Exception:
                    pass

        conf_adj = float(np.clip(g_conf + 0.15 * conf_lv + 0.10 * conf_fib, 0.0, 1.0))
        opp_adj = float(np.clip((strength * 100.0) * (1.0 + 0.25 * conf_lv + 0.15 * conf_fib), 0.0, 100.0))

        try:
            t_now = pd.to_datetime(ts)
            cfg = OperationalFilterConfig(
                fx_session_utc=(int(settings.FX_SESSION_START_UTC), int(settings.FX_SESSION_END_UTC)),
                max_atr_pct=float(settings.MAX_ATR_PCT),
                min_atr_pct=float(settings.MIN_ATR_PCT),
                news_blackout_path=str(settings.NEWS_BLACKOUT_PATH),
            )
            filt = apply_operational_filters(symbol=symbol, ts=t_now.to_pydatetime(), close=float(price), atr=base_atr, cfg=cfg)
        except Exception:
            filt = []
        if filt:
            reasons.extend(filt)
            g_dir = "neutral"
            conf_adj = float(min(conf_adj, 0.35))
            opp_adj = float(min(opp_adj, 20.0))

        ai_features = {
            "alignment": float(base_features["alignment"].iloc[-1]) if base_features is not None and not base_features.empty else 0.0,
            "slope_score": float(base_features["slope_score"].iloc[-1]) if base_features is not None and not base_features.empty else 0.0,
            "regression_slope_pct": float(base_features["regression_slope_pct"].iloc[-1]) if base_features is not None and not base_features.empty else 0.0,
            "regression_r2": float(base_features["regression_r2"].iloc[-1]) if base_features is not None and not base_features.empty else 0.0,
            "adx": float(base_features["adx"].iloc[-1]) if base_features is not None and not base_features.empty and pd.notna(base_features["adx"].iloc[-1]) else 0.0,
            "atr": float(base_features["atr"].iloc[-1]) if base_features is not None and not base_features.empty and pd.notna(base_features["atr"].iloc[-1]) else 0.0,
            "confluence_levels": float(conf_lv),
            "confluence_fibo": float(conf_fib),
            "alligator_mouth": float(ali_snap.mouth),
        }
        ai_prob = self.score_ai(ai_features)
        if ai_prob is not None:
            conf_adj = float(np.clip((0.65 * conf_adj) + (0.35 * ai_prob), 0.0, 1.0))
            reasons.append(f"AI prob(win): {ai_prob:.2f}")

        setup = classify_setups(df_feat_base=df_feat_base, frames=frames_out, base_timeframe=str(base_timeframe))
        out: Dict[str, Any] = {
            "timestamp": ts,
            "symbol": symbol,
            "provider": provider,
            "base_timeframe": base_timeframe,
            "direction": g_dir,
            "confidence": conf_adj,
            "opportunity_score": opp_adj,
            "price": float(price),
            "frames": frames_out,
            "reasons": reasons,
            "setup_primary": setup.get("setup_primary"),
            "setup_candidates": setup.get("setup_candidates"),
            "risk": {
                "entry_price": float(price),
                "sl": float(sl) if sl is not None else None,
                "tp": float(tp) if tp is not None else None,
                "atr": float(atr) if atr is not None else None,
                "risk_r": float(self.config.tp_atr_mult / max(1e-9, self.config.sl_atr_mult)) if atr is not None else None,
                "safe_exit_hint": safe_exit_hint,
                "ttl_bars": int(settings.SIGNAL_TTL_BARS),
                "valid_until": _valid_until_iso(ts, base_timeframe, int(settings.SIGNAL_TTL_BARS)),
            },
        }
        if include_debug and base_features is not None and not base_features.empty:
            last = base_features.iloc[-1]
            reg = linreg_metrics(df_base["close"].to_numpy(dtype=float)[-int(self.config.regression_window_bars):])
            reg_now = float(reg.intercept + reg.slope * (int(self.config.regression_window_bars) - 1))
            reg_p10 = float(reg.intercept + reg.slope * (int(self.config.regression_window_bars) - 1 + 10))
            reg_p50 = float(reg.intercept + reg.slope * (int(self.config.regression_window_bars) - 1 + 50))
            dist_reg = float(price - reg_now)
            vel = float(df_base["close"].iloc[-1] - df_base["close"].iloc[-11]) / 10.0 if len(df_base) >= 11 else 0.0
            bars_to_reg = None
            if abs(vel) > 1e-12:
                bars_to_reg = float(abs(dist_reg / vel))
            out["debug"] = {
                "alignment": float(last.get("alignment") or 0.0),
                "slope_score": float(last.get("slope_score") or 0.0),
                "regression": {
                    "window": int(self.config.regression_window_bars),
                    "slope_pct": float(reg.slope_pct),
                    "r2": float(reg.r2),
                    "line_now": reg_now,
                    "line_plus_10": reg_p10,
                    "line_plus_50": reg_p50,
                    "distance_to_line_now": dist_reg,
                    "bars_to_reach_line_est": bars_to_reg,
                },
                "pivots": piv,
                "supports": lv.supports[:12],
                "resistances": lv.resistances[:12],
                "confluence": conf_lv,
                "levels_relevance": lvl_summary,
                "fractals": fr,
                "fibo_horizontal": fib_h,
                "fibo_vertical_timezones": fib_t,
                "fibo_confluence": conf_fib,
                "alligator": {"direction": ali_snap.direction, "state": ali_snap.state, "mouth": ali_snap.mouth},
                "ai": {"prob_win": ai_prob, "features": ai_features},
            }
        return out

    def backtest(
        self,
        symbol: str,
        provider: str,
        base_timeframe: str,
        csv_path: Optional[str] = None,
        max_bars: Optional[int] = None,
        feature_mode: str = "full",
        starting_cash: float = 10000.0,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
        slippage_atr_pct_mult: float = 0.0,
        max_participation_pct: float = 0.10,
        trades_limit: int = 200,
        sizing_mode: str = "fixed_qty",
        fixed_qty: float = 1.0,
        risk_per_trade_pct: float = 1.0,
        max_leverage: float = 1.0,
        ai_assisted_sizing: bool = False,
        ai_risk_min_pct: float = 0.25,
        ai_risk_max_pct: float = 1.5,
        martingale_mult: float = 2.0,
        martingale_max_steps: int = 3,
        collect_signal_stats: bool = False,
        bar_magnifier: bool = False,
        magnifier_timeframe: str = "1m",
        entry_magnifier: bool = False,
        entry_magnifier_timeframe: str = "5m",
        apply_execution_gates: bool = True,
        max_equity_drawdown_pct: float = 50.0,
        free_cash_min_pct: float = 0.20,
        risk_stop_policy: str = "stop_immediate",
    ) -> Dict[str, Any]:
        df_base = self.load_ohlc(symbol=symbol, timeframe=base_timeframe, provider=provider, csv_path=csv_path)
        df_base = normalize_ohlcv(df_base)
        if max_bars is not None and max_bars > 0 and len(df_base) > int(max_bars):
            df_base = df_base.iloc[-int(max_bars):].reset_index(drop=True)
        if df_base.empty:
            return {"error": "no_data"}

        fee_bps_eff = float(fee_bps)
        if fee_bps_eff < 0:
            sym = str(symbol).replace("/", "")
            fee_bps_eff = float(
                {
                    "BTCUSDT": 2.0,
                    "ETHUSDT": 2.0,
                    "BNBUSDT": 2.0,
                    "SOLUSDT": 2.0,
                    "XRPUSDT": 2.0,
                }.get(sym, 2.0)
            )
        slip_bps = float(slippage_bps)
        slip_atr_mult = float(slippage_atr_pct_mult)
        part_pct = float(max(0.0, min(1.0, float(max_participation_pct))))

        df_feat_all = self._apply_features(df_base)
        base_state = self.frame_state(df_base, timeframe=base_timeframe)
        if base_state.empty:
            return {"error": "insufficient_data"}

        base_sec = int(_TF_SECONDS.get(str(base_timeframe), 0))
        mag_tf = str(magnifier_timeframe or "").strip()
        mag_sec = int(_TF_SECONDS.get(mag_tf, 0))
        use_mag = bool(bar_magnifier and mag_tf in TF_TO_PANDAS_RULE and base_sec > 0 and mag_sec > 0 and mag_sec < base_sec)
        mag_df = pd.DataFrame()
        mag_times: Optional[np.ndarray] = None
        mag_open: Optional[np.ndarray] = None
        mag_high: Optional[np.ndarray] = None
        mag_low: Optional[np.ndarray] = None
        mag_close: Optional[np.ndarray] = None
        if use_mag:
            try:
                mag_df = self.load_ohlc(symbol=symbol, timeframe=mag_tf, provider=provider, csv_path=None)
                mag_df = normalize_ohlcv(mag_df)
                if not mag_df.empty:
                    mag_times = pd.to_datetime(mag_df["datetime"]).to_numpy(dtype="datetime64[ns]")
                    mag_open = mag_df["open"].to_numpy(dtype=float)
                    mag_high = mag_df["high"].to_numpy(dtype=float)
                    mag_low = mag_df["low"].to_numpy(dtype=float)
                    mag_close = mag_df["close"].to_numpy(dtype=float)
                else:
                    use_mag = False
            except Exception:
                use_mag = False

        entry_mag_tf = str(entry_magnifier_timeframe or "").strip()
        entry_mag_sec = int(_TF_SECONDS.get(str(entry_mag_tf), 0))
        use_entry_mag = bool(entry_magnifier and entry_mag_tf in TF_TO_PANDAS_RULE and base_sec > 0 and entry_mag_sec > 0 and entry_mag_sec < base_sec)
        entry_mag_df = pd.DataFrame()
        entry_mag_feat = pd.DataFrame()
        entry_mag_times: Optional[np.ndarray] = None
        if use_entry_mag:
            try:
                entry_mag_df = self.load_ohlc(symbol=symbol, timeframe=entry_mag_tf, provider=provider, csv_path=None)
                entry_mag_df = normalize_ohlcv(entry_mag_df)
                if entry_mag_df.empty:
                    use_entry_mag = False
                else:
                    entry_mag_feat = self._apply_features(entry_mag_df)
                    entry_mag_times = pd.to_datetime(entry_mag_df["datetime"]).to_numpy(dtype="datetime64[ns]")
            except Exception:
                use_entry_mag = False

        htfs = ["4h", "1d", "1w"]
        ht_states: Dict[str, pd.DataFrame] = {}
        for tf in htfs:
            if tf == base_timeframe:
                continue
            rule = TF_TO_PANDAS_RULE[tf]
            st = self.frame_state(resample_ohlcv(df_base, rule=rule), timeframe=tf)
            if not st.empty:
                ht_states[tf] = st

        base_times = pd.to_datetime(base_state["datetime"]).to_numpy(dtype="datetime64[ns]")
        ht_index: Dict[str, np.ndarray] = {}
        ht_dir: Dict[str, np.ndarray] = {}
        ht_conf: Dict[str, np.ndarray] = {}
        ht_align: Dict[str, np.ndarray] = {}
        ht_valid: Dict[str, np.ndarray] = {}
        for tf, st in ht_states.items():
            tarr = pd.to_datetime(st["datetime"]).to_numpy(dtype="datetime64[ns]")
            ht_index[tf] = tarr
            ht_dir[tf] = st["direction"].to_numpy()
            ht_conf[tf] = st["confidence"].to_numpy(dtype=float)
            ht_align[tf] = st["alignment"].to_numpy(dtype=float)
            ht_valid[tf] = (st["slope_score"].notna() & st["alignment"].notna() & st["regression_r2"].notna()).to_numpy()

        def get_ht_state(tf: str, t: np.datetime64) -> Tuple[str, float, bool]:
            idx = ht_index.get(tf)
            if idx is None or len(idx) == 0:
                return "neutral", 0.0, False
            j = int(np.searchsorted(idx, t, side="right") - 1)
            if j < 0:
                return "neutral", 0.0, False
            return str(ht_dir[tf][j]), float(ht_conf[tf][j]), bool(ht_valid[tf][j])

        def get_ht_alignment(tf: str, t: np.datetime64) -> float:
            idx = ht_index.get(tf)
            if idx is None or len(idx) == 0:
                return 0.0
            j = int(np.searchsorted(idx, t, side="right") - 1)
            if j < 0:
                return 0.0
            try:
                v = float(ht_align[tf][j])
                return float(v) if np.isfinite(v) else 0.0
            except Exception:
                return 0.0

        timing_tf = str(self.config.timing_timeframe or "").strip()
        timing_state: Optional[pd.DataFrame] = None
        timing_index: Optional[np.ndarray] = None
        timing_dir: Optional[np.ndarray] = None
        timing_conf: Optional[np.ndarray] = None
        timing_valid: Optional[np.ndarray] = None
        try:
            if timing_tf in TF_TO_PANDAS_RULE and str(provider).lower() != "csv":
                base_sec = int(_TF_SECONDS.get(str(base_timeframe), 0))
                timing_sec = int(_TF_SECONDS.get(str(timing_tf), 0))
                if base_sec > 0 and timing_sec > 0 and timing_sec < base_sec:
                    df_t = self.load_ohlc(symbol=symbol, timeframe=timing_tf, provider=provider, csv_path=None)
                    df_t = normalize_ohlcv(df_t)
                    if not df_t.empty and len(df_t) >= 200:
                        timing_state = self.frame_state(df_t, timeframe=timing_tf)
                        if timing_state is not None and not timing_state.empty:
                            timing_index = pd.to_datetime(timing_state["datetime"]).to_numpy(dtype="datetime64[ns]")
                            timing_dir = timing_state["direction"].to_numpy()
                            timing_conf = timing_state["confidence"].to_numpy(dtype=float)
                            timing_valid = (timing_state["slope_score"].notna() & timing_state["alignment"].notna() & timing_state["regression_r2"].notna()).to_numpy()
        except Exception:
            timing_state = None

        def get_timing_state(t: np.datetime64) -> Tuple[str, float, bool]:
            if timing_index is None or timing_dir is None or timing_conf is None or timing_valid is None or len(timing_index) == 0:
                return "neutral", 0.0, False
            j = int(np.searchsorted(timing_index, t, side="right") - 1)
            if j < 0:
                return "neutral", 0.0, False
            return str(timing_dir[j]), float(timing_conf[j]), bool(timing_valid[j])

        cash = float(starting_cash)
        peak_cash = float(cash)
        equity_curve: List[float] = []
        trades: List[Dict[str, Any]] = []
        side: Optional[str] = None
        entry = None
        entry_time: Optional[pd.Timestamp] = None
        entry_i: Optional[int] = None
        entry_sub_index: Optional[int] = None
        entry_kind: str = ""
        sl = None
        tp = None
        be_done = False
        qty = 1.0
        p1_done = False
        p2_done = False
        pending_features: Dict[str, float] = {}
        entry_meta: Dict[str, Any] = {}
        mg_step = 0
        signals_raw_total = 0
        signals_raw_buy = 0
        signals_raw_sell = 0
        signals_entry_total = 0
        signals_entry_buy = 0
        signals_entry_sell = 0
        signals_by_month_raw: Dict[str, int] = {}
        signals_by_month_entry: Dict[str, int] = {}
        gates_timing_blocked = 0
        apply_gates = bool(apply_execution_gates)

        risk_policy_eff = str(risk_stop_policy)
        if risk_policy_eff not in ("stop_immediate", "stop_no_new_trades", "stop_after_close"):
            risk_policy_eff = "stop_immediate"
        risk_cfg = RiskStopConfig(
            max_equity_drawdown_pct=float(max_equity_drawdown_pct),
            free_cash_min_pct=float(free_cash_min_pct),
            policy=cast(RiskStopPolicy, risk_policy_eff),
        )
        risk_triggered = False
        risk_reason = ""
        risk_policy = str(risk_policy_eff)
        risk_stop_at_index: Optional[int] = None
        risk_stop_at_time: Optional[str] = None
        block_new_trades = False

        price_arr = base_state["close"].to_numpy(dtype=float)
        open_arr = df_base["open"].to_numpy(dtype=float)
        high_arr = df_base["high"].to_numpy(dtype=float)
        low_arr = df_base["low"].to_numpy(dtype=float)
        vol_arr = pd.to_numeric(df_base.get("volume"), errors="coerce").fillna(0.0).to_numpy(dtype=float)
        atr_arr = pd.to_numeric(base_state.get("atr"), errors="coerce").to_numpy(dtype=float)
        dir_arr = base_state["direction"].to_numpy()
        conf_arr = base_state["confidence"].to_numpy(dtype=float)
        dt_arr = pd.to_datetime(base_state["datetime"]).to_numpy()
        comp_arr = pd.to_numeric(base_state.get("ema_compression"), errors="coerce").to_numpy(dtype=float)
        align_arr = pd.to_numeric(base_state.get("alignment"), errors="coerce").to_numpy(dtype=float)
        trend_age_arr = np.zeros(len(base_state), dtype=int)
        run = 0
        prev = ""
        for j in range(len(trend_age_arr)):
            d = str(dir_arr[j])
            if d in ("buy", "sell") and d == prev:
                run += 1
            elif d in ("buy", "sell"):
                run = 1
            else:
                run = 0
            trend_age_arr[j] = int(run)
            prev = d

        fractal_low_last = np.full(len(df_base), np.nan, dtype=float)
        fractal_high_last = np.full(len(df_base), np.nan, dtype=float)
        if bool(self.config.structure_trailing):
            try:
                f = fractals(df_base, lookback=int(self.config.structure_trailing_lookback))
                cur_l = np.nan
                cur_h = np.nan
                fh = f["fractal_high"].to_numpy(dtype=bool)
                fl = f["fractal_low"].to_numpy(dtype=bool)
                for j in range(len(df_base)):
                    if bool(fl[j]):
                        cur_l = float(low_arr[j])
                    if bool(fh[j]):
                        cur_h = float(high_arr[j])
                    fractal_low_last[j] = float(cur_l) if np.isfinite(cur_l) else np.nan
                    fractal_high_last[j] = float(cur_h) if np.isfinite(cur_h) else np.nan
            except Exception:
                pass

        win_streak = 0
        pyramid_adds = 0
        qty_initial = 0.0
        signal_age = 0
        op_cfg = OperationalFilterConfig(
            fx_session_utc=(int(settings.FX_SESSION_START_UTC), int(settings.FX_SESSION_END_UTC)),
            max_atr_pct=float(settings.MAX_ATR_PCT),
            min_atr_pct=float(settings.MIN_ATR_PCT),
            news_blackout_path=str(settings.NEWS_BLACKOUT_PATH),
        )

        def _mag_slice(i: int) -> tuple[int, int]:
            if mag_times is None:
                return (0, 0)
            try:
                t0 = pd.to_datetime(dt_arr[i]).to_datetime64()
                t1 = (pd.to_datetime(dt_arr[i]) + timedelta(seconds=int(base_sec))).to_datetime64()
                l = int(np.searchsorted(mag_times, t0, side="left"))
                r = int(np.searchsorted(mag_times, t1, side="left"))
                return (l, r)
            except Exception:
                return (0, 0)

        def _entry_mag_slice(i: int) -> tuple[int, int]:
            if entry_mag_times is None:
                return (0, 0)
            try:
                t0 = pd.to_datetime(dt_arr[i]).to_datetime64()
                t1 = (pd.to_datetime(dt_arr[i]) + timedelta(seconds=int(base_sec))).to_datetime64()
                l = int(np.searchsorted(entry_mag_times, t0, side="left"))
                r = int(np.searchsorted(entry_mag_times, t1, side="left"))
                return (l, r)
            except Exception:
                return (0, 0)

        def _path_points(o: float, h: float, l: float, c: float) -> List[float]:
            if float(c) >= float(o):
                return [float(o), float(h), float(l), float(c)]
            return [float(o), float(l), float(h), float(c)]

        def _apply_slippage(px: float, side: str, is_entry: bool, atr_pct_v: float, qty_v: float, vol_v: float) -> float:
            bps = float(slip_bps)
            bps += float(slip_atr_mult) * float(atr_pct_v)
            if vol_v > 0 and qty_v > 0:
                bps += float(50.0 * max(0.0, (qty_v / max(1e-9, float(vol_v))) - float(part_pct)))
            s = str(side)
            if is_entry:
                if s == "buy":
                    return float(px) * (1.0 + bps / 10000.0)
                return float(px) * (1.0 - bps / 10000.0)
            if s == "buy":
                return float(px) * (1.0 - bps / 10000.0)
            return float(px) * (1.0 + bps / 10000.0)

        entry_mode = str(self.config.entry_mode or "hybrid")

        for i in range(60, len(base_state)):
            t = base_times[i]
            base_dir = str(dir_arr[i])
            base_conf = float(conf_arr[i])
            base_valid = bool(pd.notna(base_state["slope_score"].iloc[i]) and pd.notna(base_state["alignment"].iloc[i]) and pd.notna(base_state["regression_r2"].iloc[i]))
            states: Dict[str, Dict[str, Any]] = {base_timeframe: {"direction": base_dir, "confidence": base_conf, "valid": base_valid}}
            for tf in htfs:
                d_tf, c_tf, v_tf = get_ht_state(tf, t)
                states[tf] = {"direction": d_tf, "confidence": c_tf, "valid": v_tf}
            g_dir, g_conf, _ = self._vote(states)
            price = float(price_arr[i])
            atr_v = float(atr_arr[i]) if np.isfinite(atr_arr[i]) else None

            floating = 0.0
            if side is not None and entry is not None:
                sign = 1.0 if side == "buy" else -1.0
                floating = (float(price) - float(entry)) * sign * float(qty)
            equity_now = float(cash + floating)
            rs = apply_risk_stop(
                cfg=risk_cfg,
                starting_cash=float(starting_cash),
                cash=float(cash),
                equity=float(equity_now),
                has_open_position=bool(side is not None),
            )
            if rs.triggered:
                risk_triggered = True
                risk_reason = str(rs.reason)
                risk_policy = str(rs.policy)
                block_new_trades = bool(rs.block_new_trades)
                if risk_stop_at_index is None:
                    risk_stop_at_index = int(i)
                    risk_stop_at_time = pd.to_datetime(dt_arr[i]).isoformat()
                if rs.should_terminate:
                    break
            if g_dir != "neutral" and g_dir == base_dir and g_conf >= float(self.config.min_confidence):
                signal_age += 1
            else:
                signal_age = 0
            if collect_signal_stats and g_dir != "neutral" and g_conf >= float(self.config.min_confidence):
                signals_raw_total += 1
                if g_dir == "buy":
                    signals_raw_buy += 1
                elif g_dir == "sell":
                    signals_raw_sell += 1
                try:
                    m = pd.to_datetime(dt_arr[i]).strftime("%Y-%m")
                    signals_by_month_raw[m] = int(signals_by_month_raw.get(m, 0)) + 1
                except Exception:
                    pass

            if side is None:
                if block_new_trades:
                    equity_curve.append(float(cash))
                    continue
                if g_dir != "neutral" and g_dir == base_dir and g_conf >= float(self.config.min_confidence) and atr_v:
                    higher_ok = True
                    if bool(self.config.confirm_higher_tfs):
                        for tf_req in ("4h", "1d", "1w"):
                            st_req = states.get(tf_req) or {}
                            if st_req.get("valid") is True:
                                d_req = str(st_req.get("direction") or "neutral")
                                if d_req != g_dir:
                                    higher_ok = False
                                    break
                    if not higher_ok:
                        equity_curve.append(float(cash))
                        continue
                    if timing_state is not None and timing_index is not None:
                        td, tc, tv = get_timing_state(t)
                        if tv and str(td) != g_dir:
                            equity_curve.append(float(cash))
                            continue
                        if tv and float(tc) < float(self.config.timing_min_confidence):
                            equity_curve.append(float(cash))
                            continue
                    try:
                        ts_dt = pd.to_datetime(dt_arr[i]).to_pydatetime()
                        filt = apply_operational_filters(symbol=symbol, ts=ts_dt, close=float(price), atr=float(atr_v), cfg=op_cfg)
                        if filt:
                            equity_curve.append(float(cash))
                            continue
                    except Exception:
                        pass
                    trend_age = int(trend_age_arr[i])
                    if trend_age < int(self.config.trend_age_min_bars) or trend_age > int(self.config.trend_age_max_bars):
                        equity_curve.append(float(cash))
                        continue
                    try:
                        comp_v = float(comp_arr[i]) if np.isfinite(comp_arr[i]) else None
                        if comp_v is not None and float(comp_v) > float(self.config.ema_compression_max):
                            equity_curve.append(float(cash))
                            continue
                    except Exception:
                        pass

                    if apply_gates:
                        try:
                            comp_eff = float(comp_v) if comp_v is not None else 0.0
                            tg = timing_gate(trend_age_bars=int(trend_age), ema_compression=float(comp_eff), base_timeframe=str(base_timeframe))
                            if not tg.ok:
                                gates_timing_blocked += 1
                                equity_curve.append(float(cash))
                                continue
                        except Exception:
                            gates_timing_blocked += 1
                            equity_curve.append(float(cash))
                            continue

                    if apply_gates:
                        try:
                            frames_min = []
                            align_base = float(base_state.get("alignment").iloc[i]) if "alignment" in base_state.columns and pd.notna(base_state.get("alignment").iloc[i]) else 0.0
                            frames_min.append(
                                {
                                    "timeframe": str(base_timeframe),
                                    "confidence": float(base_conf),
                                    "alignment": float(align_base),
                                }
                            )
                            frames_min.append({"timeframe": "4h", "alignment": float(get_ht_alignment("4h", t))})
                            frames_min.append({"timeframe": "1d", "alignment": float(get_ht_alignment("1d", t))})
                            g_struct = structural_gate(frames_min)
                            g_exec = execution_threshold_gate(frames_min, base_timeframe=str(base_timeframe))
                            if not g_struct.ok or not g_exec.ok:
                                equity_curve.append(float(cash))
                                continue
                            piv_c = pivot_points_prev_day(df_base.iloc[: i + 1])
                            lv_c = build_levels(df_base.iloc[: i + 1], atr=float(atr_v), lookback=3)
                            conf_c = float(confluence_score(price=float(price), pivots=piv_c, levels=lv_c, atr=float(atr_v)))
                            frames_min[0]["level_confluence_score"] = float(conf_c)
                            g_conf = confluence_gate(frames_min, base_timeframe=str(base_timeframe))
                            if not g_conf.ok:
                                equity_curve.append(float(cash))
                                continue
                        except Exception:
                            equity_curve.append(float(cash))
                            continue

                    entry_price = float(price)
                    entry_dt = pd.to_datetime(dt_arr[i])
                    entry_sub_idx = None
                    entry_ok = None
                    if use_entry_mag and not entry_mag_feat.empty and entry_mag_times is not None:
                        l, r = _entry_mag_slice(i)
                        if r > l:
                            for k in range(int(l), int(r)):
                                w0 = max(0, int(k) - 400)
                                ed = decide_entry(entry_mag_feat.iloc[w0 : int(k) + 1], side=g_dir, mode=entry_mode, tol_atr=float(self.config.entry_tol_atr))
                                if ed.ok:
                                    entry_price = float(entry_mag_df["close"].iloc[int(k)])
                                    entry_dt = pd.to_datetime(entry_mag_df["datetime"].iloc[int(k)])
                                    entry_sub_idx = int(k)
                                    entry_ok = ed
                                    break
                    if entry_ok is None:
                        entry_ok = decide_entry(df_feat_all.iloc[: i + 1], side=g_dir, mode=entry_mode, tol_atr=float(self.config.entry_tol_atr))
                    if not entry_ok.ok:
                        equity_curve.append(float(cash))
                        continue
                    if bool(self.config.require_rejection):
                        try:
                            if entry_sub_idx is not None:
                                o = float(entry_mag_df["open"].iloc[int(entry_sub_idx)])
                                h = float(entry_mag_df["high"].iloc[int(entry_sub_idx)])
                                l0 = float(entry_mag_df["low"].iloc[int(entry_sub_idx)])
                                c = float(entry_mag_df["close"].iloc[int(entry_sub_idx)])
                            else:
                                o = float(open_arr[i])
                                h = float(high_arr[i])
                                l0 = float(low_arr[i])
                                c = float(price_arr[i])
                            body = abs(float(c) - float(o))
                            uw = float(h) - max(float(o), float(c))
                            lw = min(float(o), float(c)) - float(l0)
                            ratio = float(self.config.min_wick_ratio)
                            ok = True
                            if g_dir == "buy":
                                ok = (float(c) > float(o)) and (float(lw) >= float(ratio) * max(1e-9, float(body)))
                            elif g_dir == "sell":
                                ok = (float(c) < float(o)) and (float(uw) >= float(ratio) * max(1e-9, float(body)))
                            if not ok:
                                equity_curve.append(float(cash))
                                continue
                        except Exception:
                            pass
                    side = g_dir
                    entry = float(entry_price)
                    entry_time = pd.to_datetime(entry_dt)
                    entry_i = i
                    entry_sub_index = entry_sub_idx
                    entry_kind = str(entry_ok.kind)
                    be_done = False
                    p1_done = False
                    p2_done = False
                    qty = 1.0
                    feat_row = base_state.iloc[i]
                    feats = {
                        "alignment": float(feat_row.get("alignment") or 0.0),
                        "slope_score": float(feat_row.get("slope_score") or 0.0),
                        "regression_slope_pct": float(feat_row.get("regression_slope_pct") or 0.0),
                        "regression_r2": float(feat_row.get("regression_r2") or 0.0),
                        "adx": float(feat_row.get("adx")) if pd.notna(feat_row.get("adx")) else 0.0,
                        "atr": float(feat_row.get("atr")) if pd.notna(feat_row.get("atr")) else 0.0,
                    }
                    mode = str(feature_mode or "full").lower()
                    if mode == "full":
                        try:
                            piv = pivot_points_prev_day(df_base.iloc[: i + 1])
                            lv = build_levels(df_base.iloc[: i + 1], atr=feats["atr"], lookback=3)
                            fib_h = fibo_horizontal(df_base.iloc[: i + 1], lookback=120)
                            feats["confluence_levels"] = float(confluence_score(price=float(price), pivots=piv, levels=lv, atr=feats["atr"]))
                            feats["confluence_fibo"] = float(fibo_confluence_score(price=float(price), fibo=fib_h, atr=feats["atr"]))
                            ali, _ = latest_alligator(df_feat_all.iloc[: i + 1])
                            feats["alligator_mouth"] = float(ali.mouth)
                        except Exception:
                            feats["confluence_levels"] = 0.0
                            feats["confluence_fibo"] = 0.0
                            feats["alligator_mouth"] = 0.0
                    else:
                        feats["confluence_levels"] = 0.0
                        feats["confluence_fibo"] = 0.0
                        feats["alligator_mouth"] = 0.0
                    pending_features = feats
                    try:
                        frames_setup = [
                            {
                                "timeframe": str(base_timeframe),
                                "direction": str(g_dir),
                                "trend_age_bars": int(trend_age_arr[i]),
                                "ema_compression": float(comp_arr[i]) if np.isfinite(comp_arr[i]) else 0.0,
                                "level_confluence_score": float(feats.get("confluence_levels") or 0.0),
                            }
                        ]
                        setup = classify_setups(df_feat_base=df_feat_all.iloc[: i + 1], frames=frames_setup, base_timeframe=str(base_timeframe), top_n=3)
                        entry_meta["setup_primary"] = str(setup.get("setup_primary") or "")
                        entry_meta["setup_candidates"] = list(setup.get("setup_candidates") or [])
                        sf = setup.get("setup_features") or {}
                        try:
                            pending_features["wick_reject_ratio"] = float(sf.get("wick_reject_ratio") or 0.0)
                        except Exception:
                            pending_features["wick_reject_ratio"] = 0.0
                        try:
                            pending_features["fractal_distance_atr"] = float(sf.get("fractal_distance_atr") or 0.0)
                        except Exception:
                            pending_features["fractal_distance_atr"] = 0.0
                    except Exception:
                        entry_meta["setup_primary"] = ""
                        entry_meta["setup_candidates"] = []
                        pending_features["wick_reject_ratio"] = 0.0
                        pending_features["fractal_distance_atr"] = 0.0
                    if side == "buy":
                        sl = entry - float(self.config.sl_atr_mult) * atr_v
                        tp = entry + float(self.config.tp_atr_mult) * atr_v
                    else:
                        sl = entry + float(self.config.sl_atr_mult) * atr_v
                        tp = entry - float(self.config.tp_atr_mult) * atr_v
                    qty = float(fixed_qty)
                    if bool(self.config.use_structure_exits) and atr_v:
                        try:
                            piv_s = pivot_points_prev_day(df_base.iloc[: i + 1])
                            lv_s = build_levels(df_base.iloc[: i + 1], atr=float(atr_v), lookback=3)
                            lvl_s = nearest_levels_summary(df_base.iloc[: i + 1], clustered=lv_s, price=float(entry), atr=float(atr_v))
                            buf_sl = float(self.config.structure_sl_buffer_atr) * float(atr_v)
                            buf_tp = float(self.config.structure_tp_buffer_atr) * float(atr_v)
                            if side == "buy":
                                ns = lvl_s.get("nearest_support")
                                nr = lvl_s.get("nearest_resistance")
                                if ns is not None:
                                    sl_lv = float(ns) - float(buf_sl)
                                    if sl_lv < float(entry):
                                        sl = float(min(float(sl), sl_lv)) if sl is not None else float(sl_lv)
                                if nr is not None:
                                    tp_lv = float(nr) - float(buf_tp)
                                    if tp_lv > float(entry):
                                        tp = float(min(float(tp), tp_lv)) if tp is not None else float(tp_lv)
                                pv_r1 = piv_s.get("R1")
                                if pv_r1 is not None and float(pv_r1) > float(entry):
                                    tp = float(min(float(tp), float(pv_r1) - float(buf_tp))) if tp is not None else float(float(pv_r1) - float(buf_tp))
                            else:
                                ns = lvl_s.get("nearest_support")
                                nr = lvl_s.get("nearest_resistance")
                                if nr is not None:
                                    sl_lv = float(nr) + float(buf_sl)
                                    if sl_lv > float(entry):
                                        sl = float(max(float(sl), sl_lv)) if sl is not None else float(sl_lv)
                                if ns is not None:
                                    tp_lv = float(ns) + float(buf_tp)
                                    if tp_lv < float(entry):
                                        tp = float(max(float(tp), tp_lv)) if tp is not None else float(tp_lv)
                                pv_s1 = piv_s.get("S1")
                                if pv_s1 is not None and float(pv_s1) < float(entry):
                                    tp = float(max(float(tp), float(pv_s1) + float(buf_tp))) if tp is not None else float(float(pv_s1) + float(buf_tp))
                        except Exception:
                            pass
                    ai_p_entry = self.score_ai(dict(pending_features))
                    sm = str(sizing_mode or "fixed_qty").lower()
                    risk_pct_used: Optional[float] = None
                    sizing_mode_used = str(sm)
                    if sm in ("fixed_risk", "risk", "ai_risk", "martingale", "anti_martingale", "antimartingale", "vol_target", "voltarget", "kelly"):
                        r = abs(float(entry) - float(sl)) if (entry is not None and sl is not None) else 0.0
                        if r > 0 and float(price) > 0 and float(cash) > 0:
                            risk_pct = float(risk_per_trade_pct)
                            if sm in ("martingale",):
                                step = int(max(0, min(int(mg_step), int(martingale_max_steps))))
                                risk_pct = float(risk_pct) * (float(martingale_mult) ** float(step))
                            if sm in ("anti_martingale", "antimartingale"):
                                step = int(max(0, min(int(win_streak), int(self.config.anti_martingale_max_steps))))
                                risk_pct = float(risk_pct) * (float(self.config.anti_martingale_mult) ** float(step))
                            if sm in ("vol_target", "voltarget"):
                                atr_pct_v = (float(atr_v) / float(entry)) * 100.0 if (atr_v and float(entry) > 0) else 0.0
                                if atr_pct_v > 0:
                                    risk_pct = float(min(float(self.config.max_risk_pct), float(self.config.vol_target_atr_pct) / float(atr_pct_v)))
                            if sm in ("kelly",):
                                if ai_p_entry is not None:
                                    b = 1.0
                                    try:
                                        rr = abs(float(tp) - float(entry)) / max(1e-9, abs(float(entry) - float(sl))) if (tp is not None and sl is not None) else 1.0
                                        b = float(max(0.1, rr))
                                    except Exception:
                                        b = 1.0
                                    f = ((float(ai_p_entry) * (float(b) + 1.0)) - 1.0) / float(b)
                                    risk_pct = float(max(0.0, min(float(self.config.max_risk_pct), float(f) * float(self.config.kelly_fraction) * 100.0)))
                            if sm == "ai_risk":
                                if ai_p_entry is None:
                                    sizing_mode_used = "fixed_risk_fallback"
                                    risk_pct = float(risk_per_trade_pct)
                                else:
                                    sizing_mode_used = "ai_risk"
                                    risk_pct = float(ai_risk_min_pct) + (float(ai_risk_max_pct) - float(ai_risk_min_pct)) * float(ai_p_entry)
                            elif bool(ai_assisted_sizing) and sm in ("fixed_risk", "risk", "martingale"):
                                if ai_p_entry is not None:
                                    risk_pct = float(ai_risk_min_pct) + (float(ai_risk_max_pct) - float(ai_risk_min_pct)) * float(ai_p_entry)
                            try:
                                peak_cash = float(max(float(peak_cash), float(cash)))
                                dd = (float(cash) - float(peak_cash)) / max(1e-9, float(peak_cash))
                                if float(dd) < 0:
                                    scale = float(max(0.2, 1.0 + (float(dd) / 0.20)))
                                    risk_pct = float(risk_pct) * float(scale)
                            except Exception:
                                pass
                            risk_pct_used = float(risk_pct)
                            risk_cash = float(cash) * (risk_pct / 100.0)
                            qty_risk = float(risk_cash / r) if r > 0 else 0.0
                            qty_max = (float(cash) * float(max_leverage)) / float(price) if float(max_leverage) > 0 else qty_risk
                            qty = float(max(0.0, min(qty_risk, qty_max)))
                    if float(self.config.ai_entry_threshold) > 0 and ai_p_entry is not None and float(ai_p_entry) < float(self.config.ai_entry_threshold):
                        side = None
                        entry = None
                        entry_time = None
                        entry_i = None
                        entry_sub_index = None
                        entry_kind = ""
                        sl = None
                        tp = None
                        be_done = False
                        qty = 1.0
                        p1_done = False
                        p2_done = False
                        pending_features = {}
                        equity_curve.append(float(cash))
                        continue
                    if float(qty) <= 0:
                        side = None
                        entry = None
                        entry_time = None
                        entry_i = None
                        entry_sub_index = None
                        entry_kind = ""
                        sl = None
                        tp = None
                        be_done = False
                        qty = 1.0
                        p1_done = False
                        p2_done = False
                        pending_features = {}
                        equity_curve.append(float(cash))
                        continue
                    try:
                        v0 = float(vol_arr[i]) if np.isfinite(vol_arr[i]) else 0.0
                        cap = float(v0) * float(part_pct)
                        if cap > 0:
                            qty = float(min(float(qty), float(cap)))
                    except Exception:
                        pass
                    if float(qty) <= 0:
                        side = None
                        entry = None
                        entry_time = None
                        entry_i = None
                        entry_sub_index = None
                        entry_kind = ""
                        sl = None
                        tp = None
                        be_done = False
                        qty = 1.0
                        p1_done = False
                        p2_done = False
                        pending_features = {}
                        equity_curve.append(float(cash))
                        continue
                    qty_initial = float(qty)
                    pyramid_adds = 0
                    try:
                        atr_e = float(atr_v) if atr_v is not None else 0.0
                        ema25 = float(df_feat_all["ema_25"].iloc[i]) if "ema_25" in df_feat_all.columns and pd.notna(df_feat_all["ema_25"].iloc[i]) else None
                        ema80 = float(df_feat_all["ema_80"].iloc[i]) if "ema_80" in df_feat_all.columns and pd.notna(df_feat_all["ema_80"].iloc[i]) else None
                        ema220 = float(df_feat_all["ema_220"].iloc[i]) if "ema_220" in df_feat_all.columns and pd.notna(df_feat_all["ema_220"].iloc[i]) else None
                        dist25 = ((float(entry) - float(ema25)) / atr_e) if (ema25 is not None and atr_e > 0) else None
                        dist80 = ((float(entry) - float(ema80)) / atr_e) if (ema80 is not None and atr_e > 0) else None
                        dist220 = ((float(entry) - float(ema220)) / atr_e) if (ema220 is not None and atr_e > 0) else None
                        w = int(max(10, int(self.config.regression_window_bars)))
                        seg = df_base["close"].iloc[max(0, i - w + 1) : i + 1].to_numpy(dtype=float)
                        reg = linreg_metrics(seg)
                        line_last = float(reg.intercept + reg.slope * (len(seg) - 1)) if len(seg) else float(entry)
                        dist_reg = ((float(entry) - float(line_last)) / atr_e) if atr_e > 0 else None
                        atr_pct = (atr_e / float(entry)) * 100.0 if (atr_e > 0 and float(entry) > 0) else 0.0
                        ts0 = pd.to_datetime(entry_time).to_pydatetime() if entry_time is not None else pd.to_datetime(dt_arr[i]).to_pydatetime()
                        hour_utc = int(ts0.hour)
                        is_weekend = 1.0 if int(ts0.weekday()) >= 5 else 0.0
                        piv = pivot_points_prev_day(df_base.iloc[: i + 1])
                        pv = piv.get("P")
                        dist_pivot = ((float(entry) - float(pv)) / atr_e) if (pv is not None and atr_e > 0) else None
                        lv_tmp = build_levels(df_base.iloc[: i + 1], atr=float(atr_e), lookback=3)
                        lv_sum = nearest_levels_summary(df_base.iloc[: i + 1], clustered=lv_tmp, price=float(entry), atr=float(atr_e))
                        ds_atr = lv_sum.get("nearest_support_distance_atr")
                        dr_atr = lv_sum.get("nearest_resistance_distance_atr")
                        entry_meta = {
                            "trend_age_bars": int(trend_age_arr[i]),
                            "signal_age_bars": int(signal_age),
                            "atr_pct": float(atr_pct),
                            "ema_compression": float(comp_arr[i]) if np.isfinite(comp_arr[i]) else None,
                            "dist_ema25_atr": float(dist25) if dist25 is not None else None,
                            "dist_ema80_atr": float(dist80) if dist80 is not None else None,
                            "dist_ema220_atr": float(dist220) if dist220 is not None else None,
                            "dist_reg_atr": float(dist_reg) if dist_reg is not None else None,
                            "hour_utc": int(hour_utc),
                            "is_weekend": float(is_weekend),
                            "dist_pivot_P_atr": float(dist_pivot) if dist_pivot is not None else None,
                            "nearest_support_distance_atr": float(ds_atr) if ds_atr is not None else None,
                            "nearest_resistance_distance_atr": float(dr_atr) if dr_atr is not None else None,
                            "h4_dir": str(states.get("4h", {}).get("direction") or ""),
                            "d1_dir": str(states.get("1d", {}).get("direction") or ""),
                            "w1_dir": str(states.get("1w", {}).get("direction") or ""),
                            "ai_prob_entry": float(ai_p_entry) if ai_p_entry is not None else None,
                            "risk_pct_used": float(risk_pct_used) if risk_pct_used is not None else None,
                            "sizing_mode_used": str(sizing_mode_used),
                            "filled_qty": float(qty),
                        }
                        pending_features.update(
                            {
                                "trend_age_bars": float(trend_age_arr[i]),
                                "signal_age_bars": float(signal_age),
                                "atr_pct": float(atr_pct),
                                "ema_compression": float(comp_arr[i]) if np.isfinite(comp_arr[i]) else 0.0,
                                "dist_ema25_atr": float(dist25) if dist25 is not None else 0.0,
                                "dist_ema80_atr": float(dist80) if dist80 is not None else 0.0,
                                "dist_ema220_atr": float(dist220) if dist220 is not None else 0.0,
                                "dist_reg_atr": float(dist_reg) if dist_reg is not None else 0.0,
                                "hour_utc": float(hour_utc),
                                "is_weekend": float(is_weekend),
                                "dist_pivot_P_atr": float(dist_pivot) if dist_pivot is not None else 0.0,
                                "nearest_support_distance_atr": float(ds_atr) if ds_atr is not None else 0.0,
                                "nearest_resistance_distance_atr": float(dr_atr) if dr_atr is not None else 0.0,
                                "ai_prob_entry": float(ai_p_entry) if ai_p_entry is not None else 0.0,
                            }
                        )
                    except Exception:
                        entry_meta = {}
                    if collect_signal_stats:
                        signals_entry_total += 1
                        if g_dir == "buy":
                            signals_entry_buy += 1
                        elif g_dir == "sell":
                            signals_entry_sell += 1
                        try:
                            m = pd.to_datetime(entry_time).strftime("%Y-%m") if entry_time is not None else pd.to_datetime(dt_arr[i]).strftime("%Y-%m")
                            signals_by_month_entry[m] = int(signals_by_month_entry.get(m, 0)) + 1
                        except Exception:
                            pass
            else:
                hi = float(high_arr[i])
                lo = float(low_arr[i])
                bar_price = float(price_arr[i])
                if use_mag and mag_times is not None and mag_open is not None and mag_high is not None and mag_low is not None and mag_close is not None:
                    l, r = _mag_slice(i)
                    if r > l:
                        bar_price = float(mag_close[r - 1])
                        for k in range(l, r):
                            o_k = float(mag_open[k])
                            h_k = float(mag_high[k])
                            l_k = float(mag_low[k])
                            c_k = float(mag_close[k])
                            pts = _path_points(o_k, h_k, l_k, c_k)
                            for a, b in zip(pts[:-1], pts[1:]):
                                up = float(b) >= float(a)
                                seg_lo = float(a) if up else float(b)
                                seg_hi = float(b) if up else float(a)
                                if entry is not None and sl is not None and not be_done:
                                    r_be = abs(float(entry) - float(sl))
                                    if r_be > 0:
                                        if side == "buy" and seg_hi >= float(entry) + r_be:
                                            sl = float(entry)
                                            be_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - r_be:
                                            sl = float(entry)
                                            be_done = True
                                if entry is not None and sl is not None:
                                    r1 = abs(float(entry) - float(sl))
                                    if r1 > 0 and not p1_done:
                                        if side == "buy" and seg_hi >= float(entry) + r1:
                                            cash += (float(entry) + r1 - float(entry)) * qty * float(self.config.partial_1r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                                            p1_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - r1:
                                            cash += (float(entry) - (float(entry) - r1)) * qty * float(self.config.partial_1r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                                            p1_done = True
                                    if r1 > 0 and p1_done and not p2_done:
                                        if side == "buy" and seg_hi >= float(entry) + (2.0 * r1):
                                            cash += (float(entry) + (2.0 * r1) - float(entry)) * qty * float(self.config.partial_2r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                                            p2_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - (2.0 * r1):
                                            cash += (float(entry) - (float(entry) - (2.0 * r1))) * qty * float(self.config.partial_2r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                                            p2_done = True
                                if side is not None and entry is not None and atr_v is not None and sl is not None and p1_done:
                                    if side == "buy":
                                        trail = float(b) - float(self.config.trailing_atr_mult) * float(atr_v)
                                        sl = float(max(float(sl), trail))
                                    else:
                                        trail = float(b) + float(self.config.trailing_atr_mult) * float(atr_v)
                                        sl = float(min(float(sl), trail))
                                exit_price = None
                                if side == "buy":
                                    if not up and sl is not None and seg_lo <= float(sl) <= seg_hi:
                                        exit_price = float(sl)
                                    elif up and tp is not None and seg_lo <= float(tp) <= seg_hi:
                                        exit_price = float(tp)
                                    elif up and sl is not None and seg_lo <= float(sl) <= seg_hi:
                                        exit_price = float(sl)
                                    elif not up and tp is not None and seg_lo <= float(tp) <= seg_hi:
                                        exit_price = float(tp)
                                else:
                                    if up and sl is not None and seg_lo <= float(sl) <= seg_hi:
                                        exit_price = float(sl)
                                    elif not up and tp is not None and seg_lo <= float(tp) <= seg_hi:
                                        exit_price = float(tp)
                                    elif not up and sl is not None and seg_lo <= float(sl) <= seg_hi:
                                        exit_price = float(sl)
                                    elif up and tp is not None and seg_lo <= float(tp) <= seg_hi:
                                        exit_price = float(tp)
                                if exit_price is not None:
                                    price = float(exit_price)
                                    break
                                price = float(b)
                            if exit_price is not None:
                                break
                        if exit_price is not None and entry is not None and entry_time is not None and entry_i is not None:
                            exit_reason = "magnifier_exit"
                            try:
                                if sl is not None and abs(float(exit_price) - float(sl)) <= 1e-9:
                                    exit_reason = "sl"
                                elif tp is not None and abs(float(exit_price) - float(tp)) <= 1e-9:
                                    exit_reason = "tp"
                            except Exception:
                                pass
                            sign = 1.0 if side == "buy" else -1.0
                            atr_pct_v = float(entry_meta.get("atr_pct") or 0.0) if entry_meta else 0.0
                            v_in = float(vol_arr[int(entry_i)]) if entry_i is not None and np.isfinite(vol_arr[int(entry_i)]) else 0.0
                            v_out = float(vol_arr[int(i)]) if np.isfinite(vol_arr[int(i)]) else 0.0
                            entry_eff = _apply_slippage(float(entry), str(side), True, atr_pct_v, float(qty), v_in)
                            exit_eff = _apply_slippage(float(exit_price), str(side), False, atr_pct_v, float(qty), v_out)
                            gross = (float(exit_eff) - float(entry_eff)) * sign
                            fee = (fee_bps_eff / 10000.0) * (abs(float(exit_eff)) + abs(float(entry_eff))) / 2.0
                            pnl = (gross - fee) * float(qty)
                            cash += pnl
                            trades.append(
                                {
                                    "side": side,
                                    "entry_time": entry_time.isoformat(),
                                    "exit_time": pd.to_datetime(dt_arr[i]).isoformat(),
                                    "entry": float(entry_eff),
                                    "exit": float(exit_eff),
                                    "pnl": float(pnl),
                                    "bars_held": int(i - entry_i),
                                    "entry_index": int(entry_i),
                                    "exit_index": int(i),
                                    "entry_kind": str(entry_kind),
                                    "setup_primary": str((entry_meta or {}).get("setup_primary") or ""),
                                    "exit_reason": str(exit_reason),
                                    "entry_sub_index": int(entry_sub_index) if entry_sub_index is not None else None,
                                    "entry_meta": dict(entry_meta) if entry_meta else {},
                                    "_features": dict(pending_features),
                                }
                            )
                            side = None
                            entry = None
                            entry_time = None
                            entry_i = None
                            entry_kind = ""
                            entry_sub_index = None
                            entry_meta = {}
                            sl = None
                            tp = None
                            be_done = False
                            qty = 1.0
                            p1_done = False
                            p2_done = False
                            pending_features = {}
                            if str(sizing_mode or "").lower() in ("martingale",):
                                if float(pnl) < 0:
                                    mg_step = int(min(int(martingale_max_steps), int(mg_step) + 1))
                                else:
                                    mg_step = 0
                            if float(pnl) > 0:
                                win_streak = int(min(int(self.config.anti_martingale_max_steps), int(win_streak) + 1))
                            else:
                                win_streak = 0
                            pyramid_adds = 0
                            qty_initial = 0.0
                            equity_curve.append(float(cash))
                            continue
                    price = float(bar_price)
                if entry is not None and sl is not None and not be_done:
                    r = abs(float(entry) - float(sl))
                    if r > 0:
                        if side == "buy" and hi >= float(entry) + r:
                            sl = float(entry)
                            be_done = True
                        elif side == "sell" and lo <= float(entry) - r:
                            sl = float(entry)
                            be_done = True
                if entry is not None and sl is not None:
                    r = abs(float(entry) - float(sl))
                    if r > 0 and not p1_done:
                        if side == "buy" and hi >= float(entry) + r:
                            cash += (float(entry) + r - float(entry)) * qty * float(self.config.partial_1r_pct)
                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                            p1_done = True
                        elif side == "sell" and lo <= float(entry) - r:
                            cash += (float(entry) - (float(entry) - r)) * qty * float(self.config.partial_1r_pct)
                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                            p1_done = True
                    if r > 0 and p1_done and not p2_done:
                        if side == "buy" and hi >= float(entry) + (2.0 * r):
                            cash += (float(entry) + (2.0 * r) - float(entry)) * qty * float(self.config.partial_2r_pct)
                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                            p2_done = True
                        elif side == "sell" and lo <= float(entry) - (2.0 * r):
                            cash += (float(entry) - (float(entry) - (2.0 * r))) * qty * float(self.config.partial_2r_pct)
                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                            p2_done = True
                if side is not None and entry is not None and atr_v is not None and sl is not None and p1_done:
                    if side == "buy":
                        trail = float(price) - float(self.config.trailing_atr_mult) * float(atr_v)
                        sl = float(max(float(sl), trail))
                    else:
                        trail = float(price) + float(self.config.trailing_atr_mult) * float(atr_v)
                        sl = float(min(float(sl), trail))
                if bool(self.config.structure_trailing) and side is not None and entry is not None and sl is not None and atr_v is not None and p1_done:
                    try:
                        buf = float(self.config.structure_sl_buffer_atr) * float(atr_v)
                        if side == "buy" and np.isfinite(fractal_low_last[i]):
                            sl = float(max(float(sl), float(fractal_low_last[i]) - float(buf)))
                        elif side == "sell" and np.isfinite(fractal_high_last[i]):
                            sl = float(min(float(sl), float(fractal_high_last[i]) + float(buf)))
                    except Exception:
                        pass
                if bool(self.config.pyramiding_enabled) and side is not None and entry is not None and sl is not None and atr_v is not None and qty_initial > 0 and pyramid_adds < int(self.config.pyramid_max_adds):
                    try:
                        r0 = abs(float(entry) - float(sl))
                        if r0 > 0 and g_dir == side and float(g_conf) >= float(self.config.min_confidence):
                            move_r = ((float(price) - float(entry)) / r0) if side == "buy" else ((float(entry) - float(price)) / r0)
                            if float(move_r) >= float(self.config.pyramid_add_r):
                                ema25 = float(df_feat_all["ema_25"].iloc[i]) if "ema_25" in df_feat_all.columns and pd.notna(df_feat_all["ema_25"].iloc[i]) else None
                                tol = float(self.config.entry_tol_atr) * float(atr_v)
                                retest_ok = True
                                if ema25 is not None:
                                    if side == "buy":
                                        retest_ok = bool(float(low_arr[i]) <= float(ema25) + float(tol) and float(price_arr[i]) >= float(ema25))
                                    else:
                                        retest_ok = bool(float(high_arr[i]) >= float(ema25) - float(tol) and float(price_arr[i]) <= float(ema25))
                                if not retest_ok:
                                    raise RuntimeError("no_retest")
                                series = tuple(self.config.pyramid_lot_series) if self.config.pyramid_lot_series else (1.0, 1.0)
                                unit = float(qty_initial) / max(1e-9, float(series[0]))
                                leg = int(min(int(pyramid_adds) + 1, len(series) - 1))
                                add_qty = float(unit) * float(series[leg]) * float(self.config.pyramid_add_pct)
                                if add_qty > 0:
                                    new_qty = float(qty) + float(add_qty)
                                    entry = (float(entry) * float(qty) + float(price) * float(add_qty)) / max(1e-9, new_qty)
                                    qty = float(new_qty)
                                    pyramid_adds = int(pyramid_adds) + 1
                    except Exception:
                        pass
                exit_price = None
                exit_reason = None
                if exit_price is None and int(self.config.time_stop_bars) > 0 and side is not None and entry is not None and entry_i is not None and sl is not None:
                    try:
                        held = int(i - int(entry_i))
                        if held >= int(self.config.time_stop_bars):
                            r0 = abs(float(entry) - float(sl))
                            if r0 > 0:
                                sign = 1.0 if side == "buy" else -1.0
                                prog = (float(price) - float(entry)) * sign
                                if float(prog) < float(self.config.time_stop_min_r) * float(r0):
                                    exit_price = float(price)
                                    exit_reason = "time_stop"
                    except Exception:
                        pass
                if side == "buy":
                    if sl is not None and lo <= float(sl):
                        exit_price = float(sl)
                        exit_reason = "sl"
                    elif tp is not None and hi >= float(tp):
                        exit_price = float(tp)
                        exit_reason = "tp"
                else:
                    if sl is not None and hi >= float(sl):
                        exit_price = float(sl)
                        exit_reason = "sl"
                    elif tp is not None and lo <= float(tp):
                        exit_price = float(tp)
                        exit_reason = "tp"
                if exit_price is None and bool(self.config.invalidate_on_4h_flip):
                    st4h = states.get("4h") or {}
                    if st4h.get("valid") is True:
                        d4h = str(st4h.get("direction") or "neutral")
                        if d4h != side:
                            exit_price = price
                            exit_reason = "flip_4h"
                if exit_price is None and bool(self.config.invalidate_on_adx_ema_loss):
                    try:
                        adx_now = float(base_state["adx"].iloc[i]) if pd.notna(base_state["adx"].iloc[i]) else None
                        ema25 = float(df_feat_all["ema_25"].iloc[i]) if "ema_25" in df_feat_all.columns and pd.notna(df_feat_all["ema_25"].iloc[i]) else None
                        if adx_now is not None and ema25 is not None and adx_now <= float(self.config.soft_close_adx_drop):
                            if side == "buy" and float(price) < float(ema25):
                                exit_price = price
                                exit_reason = "adx_ema_loss"
                            elif side == "sell" and float(price) > float(ema25):
                                exit_price = price
                                exit_reason = "adx_ema_loss"
                    except Exception:
                        pass
                if exit_price is None and g_dir != "neutral" and g_dir != side and g_conf >= float(self.config.min_confidence):
                    exit_price = price
                    exit_reason = "signal_flip"
                if exit_price is None:
                    try:
                        adx_now = float(base_state["adx"].iloc[i]) if pd.notna(base_state["adx"].iloc[i]) else None
                        reg_slope_now = float(base_state["regression_slope_pct"].iloc[i]) if pd.notna(base_state["regression_slope_pct"].iloc[i]) else 0.0
                        if adx_now is not None and adx_now <= float(self.config.soft_close_adx_drop):
                            if side == "buy" and reg_slope_now < 0:
                                exit_price = price
                                exit_reason = "soft_close"
                            elif side == "sell" and reg_slope_now > 0:
                                exit_price = price
                                exit_reason = "soft_close"
                    except Exception:
                        pass
                if exit_price is not None and entry is not None and entry_time is not None and entry_i is not None:
                    sign = 1.0 if side == "buy" else -1.0
                    atr_pct_v = float(entry_meta.get("atr_pct") or 0.0) if entry_meta else 0.0
                    v_in = float(vol_arr[int(entry_i)]) if np.isfinite(vol_arr[int(entry_i)]) else 0.0
                    v_out = float(vol_arr[int(i)]) if np.isfinite(vol_arr[int(i)]) else 0.0
                    entry_eff = _apply_slippage(float(entry), str(side), True, atr_pct_v, float(qty), v_in)
                    exit_eff = _apply_slippage(float(exit_price), str(side), False, atr_pct_v, float(qty), v_out)
                    gross = (float(exit_eff) - float(entry_eff)) * sign
                    fee = (fee_bps_eff / 10000.0) * (abs(float(exit_eff)) + abs(float(entry_eff))) / 2.0
                    pnl = (gross - fee) * float(qty)
                    cash += pnl
                    trades.append(
                        {
                            "side": side,
                            "entry_time": entry_time.isoformat(),
                            "exit_time": pd.to_datetime(dt_arr[i]).isoformat(),
                            "entry": float(entry_eff),
                            "exit": float(exit_eff),
                            "pnl": float(pnl),
                            "bars_held": int(i - entry_i),
                            "entry_index": int(entry_i),
                            "exit_index": int(i),
                            "entry_kind": str(entry_kind),
                            "exit_reason": str(exit_reason or "unknown"),
                            "entry_sub_index": int(entry_sub_index) if entry_sub_index is not None else None,
                            "entry_meta": dict(entry_meta) if entry_meta else {},
                            "_features": dict(pending_features),
                        }
                    )
                    side = None
                    entry = None
                    entry_time = None
                    entry_i = None
                    entry_kind = ""
                    entry_sub_index = None
                    entry_meta = {}
                    sl = None
                    tp = None
                    be_done = False
                    qty = 1.0
                    p1_done = False
                    p2_done = False
                    pending_features = {}
                    if str(sizing_mode or "").lower() in ("martingale",):
                        if float(pnl) < 0:
                            mg_step = int(min(int(martingale_max_steps), int(mg_step) + 1))
                        else:
                            mg_step = 0
                    if float(pnl) > 0:
                        win_streak = int(min(int(self.config.anti_martingale_max_steps), int(win_streak) + 1))
                    else:
                        win_streak = 0
                    pyramid_adds = 0
                    qty_initial = 0.0

            floating = 0.0
            if side is not None and entry is not None:
                sign = 1.0 if side == "buy" else -1.0
                floating = (price - float(entry)) * sign * float(qty)
            equity_curve.append(float(cash + floating))

        eq = np.array(equity_curve, dtype=float) if equity_curve else np.array([starting_cash], dtype=float)
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.maximum(1e-9, peak)
        max_dd_pct = float(dd.min() * 100.0) if len(dd) else 0.0
        wins = sum(1 for t in trades if float(t["pnl"]) > 0)
        gp = sum(float(t["pnl"]) for t in trades if float(t["pnl"]) > 0)
        gl = -sum(float(t["pnl"]) for t in trades if float(t["pnl"]) < 0)
        pf = float(gp / max(1e-9, gl)) if trades else 0.0
        exit_counts: Dict[str, int] = {}
        entry_counts: Dict[str, int] = {}
        pnl_by_exit: Dict[str, float] = {}
        n_by_exit: Dict[str, int] = {}
        pnl_by_entry: Dict[str, float] = {}
        n_by_entry: Dict[str, int] = {}
        for t in trades:
            ex = str(t.get("exit_reason") or "unknown")
            ek = str(t.get("entry_kind") or "unknown")
            exit_counts[ex] = int(exit_counts.get(ex, 0)) + 1
            entry_counts[ek] = int(entry_counts.get(ek, 0)) + 1
            pnl_by_exit[ex] = float(pnl_by_exit.get(ex, 0.0)) + float(t.get("pnl") or 0.0)
            n_by_exit[ex] = int(n_by_exit.get(ex, 0)) + 1
            pnl_by_entry[ek] = float(pnl_by_entry.get(ek, 0.0)) + float(t.get("pnl") or 0.0)
            n_by_entry[ek] = int(n_by_entry.get(ek, 0)) + 1
        pnl_avg_by_exit = {k: float(pnl_by_exit.get(k, 0.0)) / max(1, int(n_by_exit.get(k, 0))) for k in exit_counts.keys()}
        pnl_avg_by_entry = {k: float(pnl_by_entry.get(k, 0.0)) / max(1, int(n_by_entry.get(k, 0))) for k in entry_counts.keys()}
        start_dt = pd.to_datetime(base_state["datetime"].iloc[0])
        end_dt = pd.to_datetime(base_state["datetime"].iloc[-1])
        days = max(1.0, float((end_dt - start_dt).days))
        cagr = -100.0
        if float(starting_cash) > 0 and float(cash) > 0:
            cagr = ((float(cash) / float(starting_cash)) ** (365.0 / days) - 1.0) * 100.0
        metrics = {
            "trades": len(trades),
            "win_rate_pct": (wins / max(1, len(trades))) * 100.0,
            "profit_factor": pf,
            "total_pnl": float(cash - starting_cash),
            "equity_last": float(cash),
            "max_drawdown_pct": max_dd_pct,
            "CAGR_pct": float(cagr),
            "exit_reason_counts": dict(exit_counts),
            "entry_kind_counts": dict(entry_counts),
            "pnl_avg_by_exit_reason": dict(pnl_avg_by_exit),
            "pnl_avg_by_entry_kind": dict(pnl_avg_by_entry),
            "gates_timing_blocked": int(gates_timing_blocked),
            "risk_stop_triggered": bool(risk_triggered),
            "risk_stop_reason": str(risk_reason),
            "risk_stop_policy": str(risk_policy),
            "risk_stop_at_index": int(risk_stop_at_index) if risk_stop_at_index is not None else None,
            "risk_stop_at_time": str(risk_stop_at_time) if risk_stop_at_time is not None else "",
            "risk_threshold_equity": float(float(starting_cash) * (1.0 - float(max_equity_drawdown_pct) / 100.0)),
            "risk_threshold_free_cash": float(float(starting_cash) * float(free_cash_min_pct)),
        }
        try:
            def _arr(key: str, only_wins: Optional[bool]) -> np.ndarray:
                vals = []
                for t in trades:
                    pnl_v = float(t.get("pnl") or 0.0)
                    if only_wins is True and pnl_v <= 0:
                        continue
                    if only_wins is False and pnl_v > 0:
                        continue
                    em = t.get("entry_meta") or {}
                    v = em.get(key)
                    if v is None:
                        continue
                    try:
                        vals.append(float(v))
                    except Exception:
                        continue
                return np.asarray(vals, dtype=float) if vals else np.asarray([], dtype=float)

            def _pct(a: np.ndarray) -> Dict[str, float]:
                if a.size == 0:
                    return {}
                return {"p50": float(np.nanpercentile(a, 50)), "p75": float(np.nanpercentile(a, 75)), "p90": float(np.nanpercentile(a, 90))}

            w_age = _arr("trend_age_bars", True)
            w_comp = _arr("ema_compression", True)
            w_ai = _arr("ai_prob_entry", True)
            report = {
                "wins": {
                    "trend_age_bars": _pct(w_age),
                    "ema_compression": _pct(w_comp),
                    "dist_ema25_atr": _pct(_arr("dist_ema25_atr", True)),
                    "dist_reg_atr": _pct(_arr("dist_reg_atr", True)),
                    "signal_age_bars": _pct(_arr("signal_age_bars", True)),
                },
                "losses": {
                    "trend_age_bars": _pct(_arr("trend_age_bars", False)),
                    "ema_compression": _pct(_arr("ema_compression", False)),
                    "dist_ema25_atr": _pct(_arr("dist_ema25_atr", False)),
                    "dist_reg_atr": _pct(_arr("dist_reg_atr", False)),
                    "signal_age_bars": _pct(_arr("signal_age_bars", False)),
                },
                "recommendations": {
                    "trend_age_max_bars": int(np.nanpercentile(w_age, 75)) if w_age.size else int(self.config.trend_age_max_bars),
                    "ema_compression_max": float(np.nanpercentile(w_comp, 75)) if w_comp.size else float(self.config.ema_compression_max),
                    "ai_entry_threshold": float(np.nanpercentile(w_ai, 60)) if w_ai.size else float(self.config.ai_entry_threshold),
                },
            }
            metrics["late_entry_report"] = report
        except Exception:
            pass
        try:
            buckets = [
                ("adx<=18", lambda x: float(x) <= 18.0),
                ("18<adx<=25", lambda x: float(x) > 18.0 and float(x) <= 25.0),
                ("adx>25", lambda x: float(x) > 25.0),
            ]
            out = {}
            for name, fn in buckets:
                pts = []
                for t in trades:
                    feats = t.get("_features") or {}
                    adx_v = feats.get("adx")
                    if adx_v is None:
                        continue
                    try:
                        if fn(float(adx_v)):
                            pts.append(float(t.get("pnl") or 0.0))
                    except Exception:
                        continue
                if not pts:
                    out[name] = {"n": 0, "pf": 0.0, "avg_pnl": 0.0}
                    continue
                gp = sum(x for x in pts if x > 0)
                gl = -sum(x for x in pts if x < 0)
                out[name] = {"n": int(len(pts)), "pf": float(gp / max(1e-9, gl)), "avg_pnl": float(sum(pts) / max(1, len(pts)))}
            metrics["regime_report"] = out
        except Exception:
            pass
        if collect_signal_stats:
            metrics.update(
                {
                    "signals_raw_total": int(signals_raw_total),
                    "signals_raw_buy": int(signals_raw_buy),
                    "signals_raw_sell": int(signals_raw_sell),
                    "signals_entry_total": int(signals_entry_total),
                    "signals_entry_buy": int(signals_entry_buy),
                    "signals_entry_sell": int(signals_entry_sell),
                    "signals_by_month_raw": dict(signals_by_month_raw),
                    "signals_by_month_entry": dict(signals_by_month_entry),
                }
            )
        return {
            "symbol": symbol,
            "provider": provider,
            "base_timeframe": base_timeframe,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "metrics": metrics,
            "trades": (trades if int(trades_limit) <= 0 else trades[-int(trades_limit) :]),
        }

    def portfolio_backtest(
        self,
        symbols: List[str],
        provider: str,
        base_timeframe: str,
        starting_cash: float = 10000.0,
        fee_bps: float = 0.0,
        max_bars: Optional[int] = None,
        max_positions: int = 3,
        per_symbol_cooldown_bars: int = 0,
        sizing_mode: str = "fixed_risk",
        risk_per_trade_pct: float = 1.0,
        max_leverage: float = 1.0,
        ai_assisted_sizing: bool = True,
        ai_risk_min_pct: float = 0.25,
        ai_risk_max_pct: float = 1.5,
        bar_magnifier: bool = False,
        magnifier_timeframe: str = "5m",
    ) -> Dict[str, Any]:
        items = [str(s).strip() for s in (symbols or []) if str(s).strip()]
        if not items:
            return {"error": "no_symbols"}
        p = str(provider or "csv")
        bt = str(base_timeframe or "1h")
        fee_bps_eff = float(fee_bps)
        if fee_bps_eff < 0:
            fee_bps_eff = 2.0

        entry_mode = str(self.config.entry_mode or "hybrid")

        per_sym = {}
        common_times: Optional[np.ndarray] = None
        for sym in items:
            df = self.load_ohlc(symbol=sym, timeframe=bt, provider=p, csv_path=None)
            df = normalize_ohlcv(df)
            if max_bars is not None and max_bars > 0 and len(df) > int(max_bars):
                df = df.iloc[-int(max_bars) :].reset_index(drop=True)
            if df.empty:
                continue
            df_feat = self._apply_features(df)
            st = self.frame_state(df, timeframe=bt)
            if st.empty:
                continue
            times = pd.to_datetime(st["datetime"]).to_numpy(dtype="datetime64[ns]")
            common_times = times if common_times is None else np.intersect1d(common_times, times)
            htfs = ["4h", "1d", "1w"]
            ht_states: Dict[str, pd.DataFrame] = {}
            for tf in htfs:
                if tf == bt:
                    continue
                rule = TF_TO_PANDAS_RULE[tf]
                st_tf = self.frame_state(resample_ohlcv(df, rule=rule), timeframe=tf)
                if not st_tf.empty:
                    ht_states[tf] = st_tf
            per_sym[sym] = {"df": df, "df_feat": df_feat, "st": st, "ht": ht_states}

        if common_times is None or len(common_times) < 100:
            return {"error": "insufficient_common_data"}

        for sym, pack in per_sym.items():
            idx = pd.DatetimeIndex(pd.to_datetime(pack["st"]["datetime"]))
            pack["map"] = idx.get_indexer(pd.to_datetime(common_times))
            try:
                m = pack["map"]
                closes = pack["st"]["close"].to_numpy(dtype=float)
                aligned_close = np.asarray([closes[int(j)] if int(j) >= 0 else np.nan for j in m], dtype=float)
                rets = np.zeros(len(aligned_close), dtype=float)
                for k in range(1, len(aligned_close)):
                    a = float(aligned_close[k - 1])
                    b = float(aligned_close[k])
                    if np.isfinite(a) and np.isfinite(b) and a > 0:
                        rets[k] = float((b / a) - 1.0)
                    else:
                        rets[k] = 0.0
                pack["ret"] = rets
            except Exception:
                pack["ret"] = np.zeros(len(common_times), dtype=float)
            ht_index = {}
            ht_dir = {}
            ht_conf = {}
            ht_align = {}
            ht_valid = {}
            for tf, st_tf in (pack.get("ht") or {}).items():
                tarr = pd.to_datetime(st_tf["datetime"]).to_numpy(dtype="datetime64[ns]")
                ht_index[tf] = tarr
                ht_dir[tf] = st_tf["direction"].to_numpy()
                ht_conf[tf] = st_tf["confidence"].to_numpy(dtype=float)
                ht_align[tf] = st_tf["alignment"].to_numpy(dtype=float)
                ht_valid[tf] = (st_tf["slope_score"].notna() & st_tf["alignment"].notna() & st_tf["regression_r2"].notna()).to_numpy()
            pack["ht_index"] = ht_index
            pack["ht_dir"] = ht_dir
            pack["ht_conf"] = ht_conf
            pack["ht_align"] = ht_align
            pack["ht_valid"] = ht_valid
            try:
                m = pack["map"]
                st = pack["st"]
                dirs = st["direction"].to_numpy()
                comps = pd.to_numeric(st.get("ema_compression"), errors="coerce").fillna(0.0).to_numpy(dtype=float)
                age = np.zeros(len(common_times), dtype=int)
                comp_aligned = np.zeros(len(common_times), dtype=float)
                run = 0
                prev = "neutral"
                for ti, j in enumerate(m):
                    if int(j) < 0:
                        age[ti] = 0
                        comp_aligned[ti] = 0.0
                        continue
                    d = str(dirs[int(j)])
                    if d in ("buy", "sell") and d == prev:
                        run += 1
                    elif d in ("buy", "sell"):
                        run = 1
                    else:
                        run = 0
                    age[ti] = int(run)
                    prev = d
                    comp_aligned[ti] = float(comps[int(j)]) if np.isfinite(float(comps[int(j)])) else 0.0
                pack["trend_age"] = age
                pack["comp"] = comp_aligned
            except Exception:
                pack["trend_age"] = np.zeros(len(common_times), dtype=int)
                pack["comp"] = np.zeros(len(common_times), dtype=float)

        base_sec = int(_TF_SECONDS.get(bt, 0))
        mag_tf = str(magnifier_timeframe or "").strip()
        mag_sec = int(_TF_SECONDS.get(mag_tf, 0))
        use_mag = bool(bar_magnifier and mag_tf in TF_TO_PANDAS_RULE and base_sec > 0 and mag_sec > 0 and mag_sec < base_sec and p.lower() != "csv")
        mag_cache: Dict[str, Dict[str, Any]] = {}
        if use_mag:
            for sym in per_sym.keys():
                try:
                    mdf = self.load_ohlc(symbol=sym, timeframe=mag_tf, provider=p, csv_path=None)
                    mdf = normalize_ohlcv(mdf)
                    if mdf.empty:
                        continue
                    mag_cache[sym] = {
                        "t": pd.to_datetime(mdf["datetime"]).to_numpy(dtype="datetime64[ns]"),
                        "o": mdf["open"].to_numpy(dtype=float),
                        "h": mdf["high"].to_numpy(dtype=float),
                        "l": mdf["low"].to_numpy(dtype=float),
                        "c": mdf["close"].to_numpy(dtype=float),
                    }
                except Exception:
                    continue

        def _mag_slice(sym: str, t0: np.datetime64) -> tuple[int, int]:
            m = mag_cache.get(sym)
            if not m:
                return (0, 0)
            t = m["t"]
            l = int(np.searchsorted(t, t0, side="left"))
            r = int(np.searchsorted(t, t0 + np.timedelta64(int(base_sec), "s"), side="left"))
            return (l, r)

        def _path_points(o: float, h: float, l: float, c: float) -> List[float]:
            if float(c) >= float(o):
                return [float(o), float(h), float(l), float(c)]
            return [float(o), float(l), float(h), float(c)]

        def _get_ht_state(pack: Dict[str, Any], tf: str, t: np.datetime64) -> Tuple[str, float, bool]:
            idx = (pack.get("ht_index") or {}).get(tf)
            if idx is None or len(idx) == 0:
                return "neutral", 0.0, False
            j = int(np.searchsorted(idx, t, side="right") - 1)
            if j < 0:
                return "neutral", 0.0, False
            return str(pack["ht_dir"][tf][j]), float(pack["ht_conf"][tf][j]), bool(pack["ht_valid"][tf][j])

        def _get_ht_alignment(pack: Dict[str, Any], tf: str, t: np.datetime64) -> float:
            idx = (pack.get("ht_index") or {}).get(tf)
            if idx is None or len(idx) == 0:
                return 0.0
            j = int(np.searchsorted(idx, t, side="right") - 1)
            if j < 0:
                return 0.0
            try:
                arr = (pack.get("ht_align") or {}).get(tf)
                if arr is None:
                    return 0.0
                v = float(arr[j])
                return float(v) if np.isfinite(v) else 0.0
            except Exception:
                return 0.0

        def _score_candidate(g_conf: float, ai_p: Optional[float], alignment: float, slope_score: float, adx: float) -> float:
            s = float(self.config.ensemble_w_conf) * float(g_conf)
            if ai_p is not None:
                s += float(self.config.ensemble_w_ai) * float(ai_p)
            s += float(self.config.ensemble_w_alignment) * float(alignment)
            s += float(self.config.ensemble_w_slope) * float(slope_score)
            s += float(self.config.ensemble_w_adx) * float(min(1.0, max(0.0, float(adx) / 50.0)))
            return float(s)

        models: Dict[str, Any] = {}
        stack_model = None
        try:
            from .model import load_model

            stack_path = os.path.join(settings.MODELS_DIR, "naira_logreg_stack.json")
            stack_model = load_model(stack_path)
        except Exception:
            stack_model = None
        for sym in per_sym.keys():
            try:
                mp = os.path.join(settings.MODELS_DIR, f"naira_logreg_{sym}_{p}_{bt}.json")
                m = load_model(mp)
                if m is not None:
                    models[sym] = m
                elif stack_model is not None:
                    models[sym] = stack_model
            except Exception:
                continue

        cash = float(starting_cash)
        equity_curve: List[float] = []
        trades: List[Dict[str, Any]] = []
        cooldown: Dict[str, int] = {s: 0 for s in per_sym.keys()}
        global_cd = 0

        positions: Dict[str, Dict[str, Any]] = {}
        start_dt = pd.to_datetime(common_times[0]).isoformat()

        for ti in range(60, len(common_times)):
            t = common_times[ti]
            global_cd = max(0, int(global_cd) - 1)
            if per_symbol_cooldown_bars > 0:
                for s in list(cooldown.keys()):
                    cooldown[s] = max(0, int(cooldown[s]) - 1)

            floating = 0.0
            for sym, pos in list(positions.items()):
                pack = per_sym.get(sym)
                if not pack:
                    continue
                i = int(pack["map"][ti])
                if i < 0:
                    continue
                df = pack["df"]
                st = pack["st"]
                hi = float(df["high"].iloc[i])
                lo = float(df["low"].iloc[i])
                price = float(st["close"].iloc[i])
                atr_v = float(st["atr"].iloc[i]) if pd.notna(st["atr"].iloc[i]) else None
                side = pos["side"]
                entry = float(pos["entry"])
                sl = pos.get("sl")
                tp = pos.get("tp")
                qty = float(pos.get("qty") or 0.0)
                be_done = bool(pos.get("be_done") or False)
                p1_done = bool(pos.get("p1_done") or False)
                p2_done = bool(pos.get("p2_done") or False)

                if use_mag and sym in mag_cache:
                    m = mag_cache[sym]
                    l, r = _mag_slice(sym, t)
                    if r > l:
                        for k in range(l, r):
                            pts = _path_points(float(m["o"][k]), float(m["h"][k]), float(m["l"][k]), float(m["c"][k]))
                            for a, b in zip(pts[:-1], pts[1:]):
                                up = float(b) >= float(a)
                                seg_lo = float(a) if up else float(b)
                                seg_hi = float(b) if up else float(a)
                                if entry and sl is not None and not be_done:
                                    r_be = abs(float(entry) - float(sl))
                                    if r_be > 0:
                                        if side == "buy" and seg_hi >= float(entry) + r_be:
                                            sl = float(entry)
                                            be_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - r_be:
                                            sl = float(entry)
                                            be_done = True
                                if entry and sl is not None:
                                    r1 = abs(float(entry) - float(sl))
                                    if r1 > 0 and not p1_done:
                                        if side == "buy" and seg_hi >= float(entry) + r1:
                                            cash += r1 * qty * float(self.config.partial_1r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                                            p1_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - r1:
                                            cash += r1 * qty * float(self.config.partial_1r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_1r_pct))
                                            p1_done = True
                                    if r1 > 0 and p1_done and not p2_done:
                                        if side == "buy" and seg_hi >= float(entry) + (2.0 * r1):
                                            cash += (2.0 * r1) * qty * float(self.config.partial_2r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                                            p2_done = True
                                        elif side == "sell" and seg_lo <= float(entry) - (2.0 * r1):
                                            cash += (2.0 * r1) * qty * float(self.config.partial_2r_pct)
                                            qty = qty * (1.0 - float(self.config.partial_2r_pct))
                                            p2_done = True
                                if side and entry and atr_v is not None and sl is not None and p1_done:
                                    if side == "buy":
                                        trail = float(b) - float(self.config.trailing_atr_mult) * float(atr_v)
                                        sl = float(max(float(sl), trail))
                                    else:
                                        trail = float(b) + float(self.config.trailing_atr_mult) * float(atr_v)
                                        sl = float(min(float(sl), trail))
                                price = float(b)

                exit_price = None
                exit_reason = None
                if side == "buy":
                    if sl is not None and lo <= float(sl):
                        exit_price = float(sl)
                        exit_reason = "sl"
                    elif tp is not None and hi >= float(tp):
                        exit_price = float(tp)
                        exit_reason = "tp"
                else:
                    if sl is not None and hi >= float(sl):
                        exit_price = float(sl)
                        exit_reason = "sl"
                    elif tp is not None and lo <= float(tp):
                        exit_price = float(tp)
                        exit_reason = "tp"
                if exit_price is None:
                    states = {bt: {"direction": str(st["direction"].iloc[i]), "confidence": float(st["confidence"].iloc[i]), "valid": True}}
                    for tf in ("4h", "1d", "1w"):
                        d_tf, c_tf, v_tf = _get_ht_state(pack, tf, t)
                        states[tf] = {"direction": d_tf, "confidence": c_tf, "valid": v_tf}
                    g_dir, g_conf, _ = self._vote(states)
                    if g_dir != "neutral" and g_dir != side and g_conf >= float(self.config.min_confidence):
                        exit_price = float(price)
                        exit_reason = "signal_flip"

                if exit_price is not None:
                    sign = 1.0 if side == "buy" else -1.0
                    gross = (float(exit_price) - float(entry)) * sign
                    fee = (fee_bps_eff / 10000.0) * (abs(float(exit_price)) + abs(float(entry))) / 2.0
                    pnl = (gross - fee) * float(qty)
                    cash += pnl
                    trades.append(
                        {
                            "symbol": sym,
                            "side": side,
                            "entry_time": pos["entry_time"],
                            "exit_time": pd.to_datetime(t).isoformat(),
                            "entry": float(entry),
                            "exit": float(exit_price),
                            "pnl": float(pnl),
                            "bars_held": int(ti - int(pos["entry_ti"])),
                            "entry_kind": str(pos.get("entry_kind") or ""),
                            "exit_reason": str(exit_reason or "unknown"),
                            "qty": float(qty),
                        }
                    )
                    positions.pop(sym, None)
                    if per_symbol_cooldown_bars > 0:
                        cooldown[sym] = int(per_symbol_cooldown_bars)
                    if int(self.config.portfolio_global_cooldown_bars) > 0:
                        global_cd = int(self.config.portfolio_global_cooldown_bars)
                else:
                    sign = 1.0 if side == "buy" else -1.0
                    floating += (float(price) - float(entry)) * sign * float(qty)
                    pos["sl"] = sl
                    pos["tp"] = tp
                    pos["qty"] = qty
                    pos["be_done"] = be_done
                    pos["p1_done"] = p1_done
                    pos["p2_done"] = p2_done

            if len(positions) < int(max_positions):
                if global_cd > 0:
                    equity_curve.append(float(cash + floating))
                    continue
                candidates = []
                for sym, pack in per_sym.items():
                    if sym in positions:
                        continue
                    if per_symbol_cooldown_bars > 0 and int(cooldown.get(sym) or 0) > 0:
                        continue
                    i = int(pack["map"][ti])
                    if i < 0:
                        continue
                    st = pack["st"]
                    base_dir = str(st["direction"].iloc[i])
                    base_conf = float(st["confidence"].iloc[i])
                    atr_v = float(st["atr"].iloc[i]) if pd.notna(st["atr"].iloc[i]) else None
                    if atr_v is None or atr_v <= 0:
                        continue
                    states = {bt: {"direction": base_dir, "confidence": base_conf, "valid": True}}
                    for tf in ("4h", "1d", "1w"):
                        d_tf, c_tf, v_tf = _get_ht_state(pack, tf, t)
                        states[tf] = {"direction": d_tf, "confidence": c_tf, "valid": v_tf}
                    g_dir, g_conf, _ = self._vote(states)
                    if g_dir == "neutral":
                        continue
                    if g_dir != base_dir:
                        continue
                    if float(g_conf) < float(self.config.min_confidence):
                        continue

                    row = st.iloc[i]
                    try:
                        align_base = float(row.get("alignment") or 0.0)
                    except Exception:
                        align_base = 0.0
                    try:
                        age_pf = int((pack.get("trend_age") or np.zeros(len(common_times), dtype=int))[ti])
                    except Exception:
                        age_pf = 0
                    try:
                        comp_pf = float((pack.get("comp") or np.zeros(len(common_times), dtype=float))[ti])
                    except Exception:
                        comp_pf = 0.0
                    try:
                        tg = timing_gate(trend_age_bars=int(age_pf), ema_compression=float(comp_pf), base_timeframe=str(base_timeframe))
                        if not tg.ok:
                            continue
                    except Exception:
                        continue
                    try:
                        piv_c = pivot_points_prev_day(pack["df"].iloc[: i + 1])
                        lv_c = build_levels(pack["df"].iloc[: i + 1], atr=float(atr_v), lookback=3)
                        conf_c = float(confluence_score(price=float(row.get("close") or 0.0), pivots=piv_c, levels=lv_c, atr=float(atr_v)))
                    except Exception:
                        conf_c = 0.0
                    frames_min = [
                        {"timeframe": str(bt), "confidence": float(base_conf), "alignment": float(align_base), "level_confluence_score": float(conf_c)},
                        {"timeframe": "4h", "alignment": float(_get_ht_alignment(pack, "4h", t))},
                        {"timeframe": "1d", "alignment": float(_get_ht_alignment(pack, "1d", t))},
                    ]
                    g_struct = structural_gate(frames_min)
                    g_conf2 = confluence_gate(frames_min, base_timeframe=str(bt))
                    g_exec = execution_threshold_gate(frames_min, base_timeframe=str(bt))
                    if not (g_struct.ok and g_conf2.ok and g_exec.ok):
                        continue

                    df_feat = pack["df_feat"]
                    w0 = max(0, int(i) - 300)
                    ed = decide_entry(df_feat.iloc[w0 : i + 1], side=g_dir, mode=entry_mode, tol_atr=float(self.config.entry_tol_atr))
                    if not ed.ok:
                        continue
                    feats = {
                        "alignment": float(row.get("alignment") or 0.0),
                        "slope_score": float(row.get("slope_score") or 0.0),
                        "regression_slope_pct": float(row.get("regression_slope_pct") or 0.0),
                        "regression_r2": float(row.get("regression_r2") or 0.0),
                        "adx": float(row.get("adx") or 0.0),
                        "atr": float(row.get("atr") or 0.0),
                        "confluence_levels": float(conf_c),
                        "confluence_fibo": 0.0,
                        "alligator_mouth": 0.0,
                    }
                    ai_p = None
                    if bool(ai_assisted_sizing):
                        m = models.get(sym)
                        if m is not None:
                            try:
                                ai_p = float(m.predict_proba(feats))
                            except Exception:
                                ai_p = None
                    if float(self.config.ai_entry_threshold) > 0 and ai_p is not None and float(ai_p) < float(self.config.ai_entry_threshold):
                        continue
                    alignment_v = float(row.get("alignment") or 0.0)
                    slope_v = float(row.get("slope_score") or 0.0)
                    adx_v = float(row.get("adx") or 0.0)
                    score = _score_candidate(float(g_conf), ai_p, alignment_v, slope_v, adx_v)
                    candidates.append((score, sym, g_dir, g_conf, atr_v, feats, ed.kind))

                candidates.sort(key=lambda x: float(x[0]), reverse=True)
                for score, sym, g_dir, g_conf, atr_v, feats, ek in candidates:
                    if len(positions) >= int(max_positions):
                        break
                    pack = per_sym[sym]
                    i = int(pack["map"][ti])
                    price = float(pack["st"]["close"].iloc[i])
                    try:
                        look = int(max(30, int(self.config.portfolio_corr_lookback)))
                        ret_c = pack.get("ret")
                        if ret_c is not None and isinstance(ret_c, np.ndarray) and len(positions) > 0:
                            a0 = max(0, int(ti) - look + 1)
                            a = ret_c[a0 : int(ti) + 1]
                            for osym in positions.keys():
                                op = per_sym.get(osym) or {}
                                b = (op.get("ret") or np.zeros_like(a))[a0 : int(ti) + 1]
                                if len(a) >= 10 and len(b) == len(a):
                                    c = float(np.corrcoef(a, b)[0, 1])
                                    if np.isfinite(c) and abs(float(c)) >= float(self.config.portfolio_max_corr):
                                        raise RuntimeError("corr_cap")
                    except Exception:
                        continue
                    sl = price - float(self.config.sl_atr_mult) * float(atr_v) if g_dir == "buy" else price + float(self.config.sl_atr_mult) * float(atr_v)
                    tp = price + float(self.config.tp_atr_mult) * float(atr_v) if g_dir == "buy" else price - float(self.config.tp_atr_mult) * float(atr_v)
                    r = abs(float(price) - float(sl))
                    qty = 0.0
                    sm = str(sizing_mode).lower()
                    if sm in ("fixed_risk", "risk", "ai_risk", "vol_target", "voltarget", "kelly") and r > 0 and cash > 0 and price > 0:
                        risk_pct = float(risk_per_trade_pct)
                        if bool(ai_assisted_sizing):
                            ai_p = None
                            m = models.get(sym)
                            if m is not None:
                                try:
                                    ai_p = float(m.predict_proba(feats))
                                except Exception:
                                    ai_p = None
                            if ai_p is not None:
                                risk_pct = float(ai_risk_min_pct) + (float(ai_risk_max_pct) - float(ai_risk_min_pct)) * float(ai_p)
                        if sm in ("vol_target", "voltarget"):
                            atr_pct_v = (float(atr_v) / float(price)) * 100.0 if float(price) > 0 else 0.0
                            if atr_pct_v > 0:
                                risk_pct = float(min(float(self.config.max_risk_pct), float(self.config.vol_target_atr_pct) / float(atr_pct_v)))
                        if sm in ("kelly",) and bool(ai_assisted_sizing):
                            ai_p = None
                            m = models.get(sym)
                            if m is not None:
                                try:
                                    ai_p = float(m.predict_proba(feats))
                                except Exception:
                                    ai_p = None
                            if ai_p is not None:
                                rr = abs(float(tp) - float(price)) / max(1e-9, abs(float(price) - float(sl)))
                                b = float(max(0.1, rr))
                                f = ((float(ai_p) * (float(b) + 1.0)) - 1.0) / float(b)
                                risk_pct = float(max(0.0, min(float(self.config.max_risk_pct), float(f) * float(self.config.kelly_fraction) * 100.0)))
                        risk_cash = float(cash) * (risk_pct / 100.0)
                        qty_risk = float(risk_cash / r)
                        qty_max = (float(cash) * float(max_leverage)) / float(price) if float(max_leverage) > 0 else qty_risk
                        qty = float(max(0.0, min(qty_risk, qty_max)))
                    else:
                        qty = 1.0
                    if qty <= 0:
                        continue
                    try:
                        notional = sum(abs(float(per_sym[s]["st"]["close"].iloc[int(per_sym[s]["map"][ti])]) * float(positions[s]["qty"])) for s in positions.keys())
                        if float(notional) + abs(float(price) * float(qty)) > float(cash) * float(max_leverage):
                            continue
                    except Exception:
                        pass
                    try:
                        majors = {"BTCUSDT", "ETHUSDT"}
                        cur_maj = sum(1 for s in positions.keys() if str(s).replace("/", "").upper() in majors)
                        cur_alt = max(0, int(len(positions)) - int(cur_maj))
                        cand_is_maj = str(sym).replace("/", "").upper() in majors
                        if cand_is_maj and int(cur_maj) >= int(self.config.portfolio_max_majors):
                            continue
                        if (not cand_is_maj) and int(cur_alt) >= int(self.config.portfolio_max_alts):
                            continue
                    except Exception:
                        pass
                    positions[sym] = {
                        "side": g_dir,
                        "entry": float(price),
                        "sl": float(sl),
                        "tp": float(tp),
                        "qty": float(qty),
                        "entry_time": pd.to_datetime(t).isoformat(),
                        "entry_ti": int(ti),
                        "entry_kind": str(ek),
                    }

            equity_curve.append(float(cash + floating))

        eq = np.asarray(equity_curve, dtype=float) if equity_curve else np.asarray([float(starting_cash)], dtype=float)
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.maximum(1e-9, peak)
        max_dd_pct = float(dd.min() * 100.0) if len(dd) else 0.0
        wins = sum(1 for t in trades if float(t["pnl"]) > 0)
        gp = sum(float(t["pnl"]) for t in trades if float(t["pnl"]) > 0)
        gl = -sum(float(t["pnl"]) for t in trades if float(t["pnl"]) < 0)
        pf = float(gp / max(1e-9, gl)) if trades else 0.0
        end_dt = pd.to_datetime(common_times[-1]).isoformat()
        days = max(1.0, float((pd.to_datetime(common_times[-1]) - pd.to_datetime(common_times[0])).days))
        cagr = -100.0
        if float(starting_cash) > 0 and float(cash) > 0:
            cagr = ((float(cash) / float(starting_cash)) ** (365.0 / days) - 1.0) * 100.0
        exit_counts: Dict[str, int] = {}
        entry_counts: Dict[str, int] = {}
        for t in trades:
            k = str(t.get("exit_reason") or "unknown")
            exit_counts[k] = int(exit_counts.get(k, 0)) + 1
            ek = str(t.get("entry_kind") or "unknown")
            entry_counts[ek] = int(entry_counts.get(ek, 0)) + 1
        return {
            "symbols": list(per_sym.keys()),
            "provider": p,
            "base_timeframe": bt,
            "start": start_dt,
            "end": end_dt,
            "metrics": {
                "trades": int(len(trades)),
                "win_rate_pct": float((wins / max(1, len(trades))) * 100.0),
                "profit_factor": float(pf),
                "equity_last": float(cash),
                "total_pnl": float(cash - float(starting_cash)),
                "max_drawdown_pct": float(max_dd_pct),
                "CAGR_pct": float(cagr),
                "open_positions_end": int(len(positions)),
                "exit_reason_counts": dict(exit_counts),
                "entry_kind_counts": dict(entry_counts),
            },
            "trades": trades[-200:],
        }
