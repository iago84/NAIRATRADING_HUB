# Setup Classifier (Multi-Label) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar un clasificador de setups multi-label (6 tipos) con scores + 2 features nuevas (wick_reject_ratio, fractal_distance_atr) y exponerlo en señales, trades (backtest) y dataset ML.

**Architecture:** Nuevo módulo `setup_classifier.py` puro y determinista. Se integra en `NairaEngine.analyze`, `multi_brain`, y en `backtest` para guardar labels en trades. `dataset.build_trade_dataset` incluirá `setup_primary` y scores top.

**Tech Stack:** Python, pandas/numpy (ya en repo), tests pytest/unittest.

---

## Mapa de cambios (archivos)

**Crear**
- `backend/app/engine/setup_classifier.py`
- `backend/tests/test_setup_classifier.py`
- `backend/tests/test_setup_integration.py`

**Modificar**
- `backend/app/engine/naira_engine.py`
- `backend/app/engine/multi_brain.py`
- `backend/app/engine/dataset.py`

---

### Task 1: Tests RED (setup_classifier API + features nuevas)

**Files:**
- Create: `backend/tests/test_setup_classifier.py`

- [ ] **Step 1: Crear test que falle por módulo inexistente**

Crear `backend/tests/test_setup_classifier.py`:

```python
import unittest
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.setup_classifier import classify_setups


class TestSetupClassifier(unittest.TestCase):
    def test_returns_candidates_sorted(self):
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2025-01-01", periods=5, freq="1h"),
                "open": [100, 101, 102, 103, 104],
                "high": [101, 102, 103, 104, 110],
                "low": [99, 100, 101, 102, 90],
                "close": [101, 102, 103, 104, 105],
                "atr": [1, 1, 1, 1, 1],
                "ema_25": [100, 101, 102, 103, 104],
                "ema_80": [99, 100, 101, 102, 103],
                "ema_compression": [1, 1, 1, 1, 1],
                "adx": [10, 10, 10, 10, 10],
                "alignment": [1, 1, 1, 1, 1],
                "trend_age_bars": [1, 1, 1, 1, 1],
                "curvature": [0, 0, 0, 0, 0],
                "slope_score": [0, 0, 0, 0, 0],
                "regression_r2": [1, 1, 1, 1, 1],
            }
        )
        frames = [{"timeframe": "1h", "level_confluence_score": 0.5}]
        r = classify_setups(df_feat_base=df, frames=frames, base_timeframe="1h")
        self.assertIn("setup_primary", r)
        self.assertTrue(isinstance(r["setup_primary"], str))
        c = r.get("setup_candidates") or []
        self.assertGreaterEqual(len(c), 1)
        scores = [float(x.get("score") or 0.0) for x in c]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test y verificar FAIL**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_setup_classifier.py`  
Expected: FAIL con `ModuleNotFoundError` o `ImportError`.

---

### Task 2: GREEN (módulo setup_classifier + scoring base)

**Files:**
- Create: `backend/app/engine/setup_classifier.py`
- Modify: `backend/app/engine/entry_rules.py`
- Test: `backend/tests/test_setup_classifier.py`

- [ ] **Step 1: Implementar setup_classifier.py (mínimo)**

Crear `backend/app/engine/setup_classifier.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .entry_rules import break_retest_entry, mean_reversion_entry, pullback_entry
from .levels import latest_fractal_levels


def _wick_reject_ratio(last: pd.Series) -> float:
    try:
        o = float(last.get("open"))
        h = float(last.get("high"))
        l = float(last.get("low"))
        c = float(last.get("close"))
        body = abs(float(c) - float(o))
        uw = float(h) - max(float(o), float(c))
        lw = min(float(o), float(c)) - float(l)
        return float(max(uw, lw) / max(1e-9, body))
    except Exception:
        return 0.0


def _fractal_distance_atr(df: pd.DataFrame) -> float:
    try:
        if df is None or df.empty or len(df) < 10:
            return 0.0
        last = df.iloc[-1]
        atr = float(last.get("atr") or 0.0)
        if atr <= 0:
            return 0.0
        fr = latest_fractal_levels(df, lookback=2)
        c = float(last.get("close") or 0.0)
        d = []
        if fr.get("fractal_high") is not None:
            d.append(abs(float(c) - float(fr["fractal_high"])))
        if fr.get("fractal_low") is not None:
            d.append(abs(float(c) - float(fr["fractal_low"])))
        if not d:
            return 0.0
        return float(min(d) / atr)
    except Exception:
        return 0.0


def _get_frame(frames: List[Dict[str, Any]], base_timeframe: str) -> Dict[str, Any]:
    by_tf = {str(f.get("timeframe") or ""): f for f in (frames or [])}
    return dict(by_tf.get(str(base_timeframe)) or (frames[-1] if frames else {}))


def _clip01(x: float) -> float:
    return float(np.clip(float(x), 0.0, 1.0))


def classify_setups(df_feat_base: pd.DataFrame, frames: List[Dict[str, Any]], base_timeframe: str, top_n: int = 3) -> Dict[str, Any]:
    df = df_feat_base
    if df is None or df.empty:
        return {"setup_primary": "unknown", "setup_candidates": []}
    last = df.iloc[-1]
    f = _get_frame(frames, base_timeframe=base_timeframe)

    trend_age = float(last.get("trend_age_bars") or 0.0)
    comp = float(last.get("ema_compression") or 0.0)
    adx = float(last.get("adx") or 0.0)
    ali = float(last.get("alignment") or 0.0)
    r2 = float(last.get("regression_r2") or 0.0)
    slope = float(last.get("slope_score") or 0.0)
    curv = float(last.get("curvature") or 0.0)
    lvl = float(f.get("level_confluence_score") or 0.0)
    wick = _wick_reject_ratio(last)
    frd = _fractal_distance_atr(df)

    side = "buy"
    try:
        d = str(f.get("direction") or last.get("direction") or "neutral")
        if d == "sell":
            side = "sell"
    except Exception:
        pass

    pull = pullback_entry(df, side=side, tol_atr=0.6)
    br = break_retest_entry(df, side=side, tol_atr=0.6)
    mr = mean_reversion_entry(df, side=side, dist_atr=1.0, min_reject_wick_ratio=1.0)

    cand = []

    breakout_score = _clip01(0.30 * (adx / 50.0) + 0.25 * ali + 0.20 * r2 + 0.15 * _clip01(abs(slope) / 2.0) + 0.10 * _clip01(max(0.0, 2.0 - comp) / 2.0))
    breakout_score *= _clip01(max(0.0, 3.0 - trend_age) / 3.0)
    cand.append({"type": "breakout", "score": float(breakout_score), "reasons": ["momentum"], "features": {"adx": adx, "alignment": ali, "r2": r2, "ema_compression": comp, "trend_age_bars": trend_age}})

    br_score = 1.0 if br.ok else _clip01(max(0.0, 2.0 - frd) / 2.0)
    cand.append({"type": "break_retest", "score": float(br_score), "reasons": ["break_retest" if br.ok else "near_fractal"], "features": {"fractal_distance_atr": frd}})

    pb_ema_score = 1.0 if pull.ok else 0.0
    cand.append({"type": "pullback_ema", "score": float(pb_ema_score), "reasons": ["ema_pullback" if pull.ok else "no_pullback"], "features": {}})

    pb_lvl_score = _clip01(lvl)
    cand.append({"type": "pullback_level", "score": float(pb_lvl_score), "reasons": ["level_confluence"], "features": {"level_confluence_score": lvl}})

    mr_score = 1.0 if mr.ok else 0.0
    mr_score *= _clip01(max(0.0, 3.0 - (adx / 10.0)) / 3.0)
    mr_score *= _clip01(min(2.5, wick) / 2.5)
    cand.append({"type": "mean_reversion", "score": float(mr_score), "reasons": ["mr_reject" if mr.ok else "no_reject"], "features": {"wick_reject_ratio": wick}})

    ex_score = _clip01(max(0.0, trend_age - 6.0) / 6.0) * _clip01(max(0.0, comp - 3.0) / 3.0) * _clip01(min(2.5, wick) / 2.5) * _clip01(min(1.0, abs(curv) * 50.0))
    cand.append({"type": "exhaustion", "score": float(ex_score), "reasons": ["late+compressed"], "features": {"trend_age_bars": trend_age, "ema_compression": comp, "wick_reject_ratio": wick, "curvature": curv}})

    cand.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    top = cand[: max(1, int(top_n))]
    primary = str(top[0].get("type") or "unknown") if top else "unknown"
    return {"setup_primary": primary, "setup_candidates": top, "setup_features": {"wick_reject_ratio": wick, "fractal_distance_atr": frd}}
```

- [ ] **Step 2: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_setup_classifier.py`  
Expected: PASS.

---

### Task 3: Integración en `analyze` y `multi_brain`

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Modify: `backend/app/engine/multi_brain.py`
- Create: `backend/tests/test_setup_integration.py`

- [ ] **Step 1: analyze añade setup**

En `NairaEngine.analyze` tras `frames_out.append(st_public)` y antes de `out`:
- llamar `classify_setups(df_feat_base=st_df_base_features_like, frames=frames_out, base_timeframe=base_timeframe)`
- añadir `setup_primary` y `setup_candidates` al `out`

- [ ] **Step 2: multi_brain añade setup**

En `multi_brain.run_multi_brain`, después de gates y antes de return:
- añadir setup al `merged`

- [ ] **Step 3: Tests integración**

Crear `backend/tests/test_setup_integration.py`:

```python
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine
from app.engine.multi_brain import run_multi_brain


class TestSetupIntegration(unittest.TestCase):
    def test_analyze_includes_setup(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r = e.analyze(symbol="TEST", provider="csv", base_timeframe="1h")
        self.assertIn("setup_primary", r)
        self.assertIn("setup_candidates", r)

    def test_multi_brain_includes_setup(self):
        e = NairaEngine(data_dir=settings.DATA_DIR)
        r, _ = run_multi_brain(engine=e, symbol="TEST", provider="csv", base_timeframe="1h", tranche="T0")
        self.assertIn("setup_primary", r)
        self.assertIn("setup_candidates", r)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_setup_integration.py`  
Expected: PASS.

---

### Task 4: Guardar setup en trades (backtest) y en dataset

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Modify: `backend/app/engine/dataset.py`

- [ ] **Step 1: backtest añade setup_primary por trade**

En el punto donde se confirma una entrada (donde se setea `entry_kind` y `pending_features`):
- calcular setup con ventana `df_feat_all.iloc[: i + 1]` y `frames_min` disponibles
- guardar:
  - `entry_meta["setup_primary"]`
  - `entry_meta["setup_candidates"]` (top3)

Al registrar el trade, copiar `setup_primary` al dict del trade.

- [ ] **Step 2: dataset incluye setup_primary**

En `build_trade_dataset`, añadir:
- `setup_primary` como columna (si existe en trade)
- top scores (opcional): `setup_score_breakout`, etc. (solo si se guardan en `_features`)

- [ ] **Step 3: Run full tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

