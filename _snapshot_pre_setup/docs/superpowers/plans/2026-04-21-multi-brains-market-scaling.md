# Multi-Brains + Market Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar un motor multi-estrategia (multi-cerebros) con router por régimen, AI gate/sizing y escalado de universo por saldo/risk-budget, empezando por señales+alertas y extendiendo a backtesting.

**Architecture:** Añadir componentes puros (UniverseManager, RegimeRouter, Brain interface, Aggregator, AIGate) y conectarlos en `scanner_service` + endpoints NAIRA. En backtest, reutilizar el mismo pipeline para decidir entradas por cerebro/régimen.

**Tech Stack:** Python, FastAPI, pandas/numpy, tests con unittest/pytest (ya existente en repo).

---

## Mapa de cambios (archivos)

**Crear**
- `backend/app/engine/universe.py`
- `backend/app/engine/regime_router.py`
- `backend/app/engine/ai_gate.py`
- `backend/app/engine/ensemble.py`
- `backend/app/engine/brains/__init__.py`
- `backend/app/engine/brains/types.py`
- `backend/app/engine/brains/trend.py`
- `backend/app/engine/brains/pullback.py`
- `backend/app/engine/brains/breakout.py`
- `backend/app/engine/brains/mean_reversion.py`
- `backend/app/engine/multi_brain.py`
- `backend/data/watchlists/crypto_top2.json`
- `backend/data/watchlists/crypto_top10.json`
- `backend/data/watchlists/crypto_top30.json`
- `backend/data/watchlists/crypto_top100.json`
- `backend/data/watchlists/fx_micro.json`
- `backend/data/watchlists/fx_majors.json`
- `backend/data/watchlists/fx_majors_minors.json`
- `backend/data/watchlists/metals.json`
- `backend/tests/test_universe.py`
- `backend/tests/test_regime_router.py`
- `backend/tests/test_ensemble.py`
- `backend/tests/test_ai_gate.py`
- `backend/tests/test_multi_brain_signal.py`

**Modificar**
- `backend/app/core/config.py`
- `backend/app/services/scanner_service.py`
- `backend/app/api/v1/endpoints/naira.py`
- `backend/app/engine/naira_engine.py`
- `README.md`

---

### Task 1: Configuración de escalado (umbrales y defaults)

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_universe.py`

- [ ] **Step 1: Añadir settings de escalado por asset**

Agregar a `Settings` (valores por defecto acordados):

```python
BALANCE_USDT: float = float(_env("BALANCE_USDT", "0"))

CRYPTO_T0_MAX: float = float(_env("CRYPTO_T0_MAX", "200"))
CRYPTO_T1_MAX: float = float(_env("CRYPTO_T1_MAX", "1000"))
CRYPTO_T2_MAX: float = float(_env("CRYPTO_T2_MAX", "5000"))

FX_T0_MAX: float = float(_env("FX_T0_MAX", "500"))
FX_T1_MAX: float = float(_env("FX_T1_MAX", "2000"))
FX_T2_MAX: float = float(_env("FX_T2_MAX", "10000"))
```

- [ ] **Step 2: Añadir settings para AI Gate por tramo**

```python
AI_GATE_T0: float = float(_env("AI_GATE_T0", "0.62"))
AI_GATE_T1: float = float(_env("AI_GATE_T1", "0.58"))
AI_GATE_T2: float = float(_env("AI_GATE_T2", "0.54"))
AI_GATE_T3: float = float(_env("AI_GATE_T3", "0.50"))
```

- [ ] **Step 3: Ejecutar tests existentes**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): add balance scaling and ai gate settings"
```

---

### Task 2: UniverseManager (símbolos por tramo y por asset)

**Files:**
- Create: `backend/app/engine/universe.py`
- Create: `backend/data/watchlists/*.json`
- Test: `backend/tests/test_universe.py`

- [ ] **Step 1: Crear watchlists JSON (estáticos, editables)**

Crear archivos con listas reales (sin placeholders), por ejemplo:

`backend/data/watchlists/crypto_top2.json`
```json
["BTCUSDT","ETHUSDT"]
```

`backend/data/watchlists/crypto_top10.json`
```json
["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","TRXUSDT","LINKUSDT","AVAXUSDT"]
```

`backend/data/watchlists/crypto_top30.json`
```json
["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","TRXUSDT","LINKUSDT","AVAXUSDT","TONUSDT","DOTUSDT","MATICUSDT","LTCUSDT","BCHUSDT","SHIBUSDT","ATOMUSDT","NEARUSDT","ICPUSDT","FILUSDT","APTUSDT","ARBUSDT","OPUSDT","INJUSDT","ETCUSDT","RNDRUSDT","IMXUSDT","SUIUSDT","SEIUSDT","XLMUSDT"]
```

`backend/data/watchlists/crypto_top100.json` (incluir 100 tickers; si se desea, se puede generar en un PR posterior, pero este plan requiere una lista completa).

FX/Metales:

`backend/data/watchlists/fx_micro.json`
```json
["EURUSD"]
```

`backend/data/watchlists/fx_majors.json`
```json
["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD"]
```

`backend/data/watchlists/fx_majors_minors.json`
```json
["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","CHFJPY","EURAUD","GBPAUD"]
```

`backend/data/watchlists/metals.json`
```json
["XAUUSD","XAGUSD"]
```

- [ ] **Step 2: Implementar UniverseManager**

Crear `backend/app/engine/universe.py`:

```python
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
```

- [ ] **Step 3: Tests de UniverseManager**

Crear `backend/tests/test_universe.py`:

```python
import unittest
from pathlib import Path
import tempfile
import json

from app.engine.universe import UniverseManager, tranche_for_balance


class TestUniverse(unittest.TestCase):
    def test_tranche_crypto(self):
        self.assertEqual(tranche_for_balance("crypto", 0), "T0")
        self.assertEqual(tranche_for_balance("crypto", 199), "T0")
        self.assertEqual(tranche_for_balance("crypto", 200), "T1")
        self.assertEqual(tranche_for_balance("crypto", 999), "T1")
        self.assertEqual(tranche_for_balance("crypto", 1000), "T2")
        self.assertEqual(tranche_for_balance("crypto", 4999), "T2")
        self.assertEqual(tranche_for_balance("crypto", 5000), "T3")

    def test_universe_load(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            wl = base / "watchlists"
            wl.mkdir(parents=True, exist_ok=True)
            (wl / "crypto_top2.json").write_text(json.dumps(["BTCUSDT","ETHUSDT"]), encoding="utf-8")
            um = UniverseManager(data_dir=str(base))
            self.assertEqual(um.symbols("crypto", "T0"), ["BTCUSDT","ETHUSDT"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/universe.py backend/data/watchlists backend/tests/test_universe.py
git commit -m "feat(universe): add tranche-based universes by asset"
```

---

### Task 3: RegimeRouter (trend/range/transition → cerebros activos)

**Files:**
- Create: `backend/app/engine/regime_router.py`
- Test: `backend/tests/test_regime_router.py`

- [ ] **Step 1: Implementar router puro (sin engine)**

`backend/app/engine/regime_router.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any, List, Tuple

Regime = Literal["trend", "range", "transition"]
BrainId = Literal["trend", "pullback", "breakout", "mean_reversion"]


@dataclass(frozen=True)
class ActiveBrains:
    dominant: BrainId
    secondary: BrainId | None = None


def _frame_by_tf(frames: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in frames or []:
        tf = str(f.get("timeframe") or "")
        if tf:
            out[tf] = dict(f)
    return out


def classify_regime(frames: List[Dict[str, Any]]) -> Regime:
    by_tf = _frame_by_tf(frames)
    f = by_tf.get("4h") or by_tf.get("1d") or {}
    adx = float(f.get("adx") or 0.0)
    comp = float(f.get("ema_compression") or 0.0)
    slope = float(f.get("slope_score") or 0.0)
    trending = (adx >= 18.0) and (abs(slope) >= 0.05) and (comp <= 3.0)
    ranging = (adx <= 14.0) and (comp >= 3.5)
    if trending:
        return "trend"
    if ranging:
        return "range"
    return "transition"


def pick_brains(regime: Regime) -> ActiveBrains:
    if regime == "trend":
        return ActiveBrains(dominant="trend", secondary="pullback")
    if regime == "range":
        return ActiveBrains(dominant="mean_reversion", secondary=None)
    return ActiveBrains(dominant="breakout", secondary="trend")
```

- [ ] **Step 2: Tests**

`backend/tests/test_regime_router.py`:

```python
import unittest
from app.engine.regime_router import classify_regime, pick_brains


class TestRegimeRouter(unittest.TestCase):
    def test_trend(self):
        frames = [{"timeframe":"4h","adx":25.0,"ema_compression":2.0,"slope_score":0.2}]
        self.assertEqual(classify_regime(frames), "trend")
        self.assertEqual(pick_brains("trend").dominant, "trend")

    def test_range(self):
        frames = [{"timeframe":"4h","adx":10.0,"ema_compression":5.0,"slope_score":0.01}]
        self.assertEqual(classify_regime(frames), "range")
        self.assertEqual(pick_brains("range").dominant, "mean_reversion")

    def test_transition(self):
        frames = [{"timeframe":"4h","adx":16.0,"ema_compression":3.1,"slope_score":0.02}]
        self.assertEqual(classify_regime(frames), "transition")
        self.assertEqual(pick_brains("transition").dominant, "breakout")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/regime_router.py backend/tests/test_regime_router.py
git commit -m "feat(router): add regime classification and brain selection"
```

---

### Task 4: AI Gate (umbral por tramo) + tests

**Files:**
- Create: `backend/app/engine/ai_gate.py`
- Test: `backend/tests/test_ai_gate.py`

- [ ] **Step 1: Implementar ai gate**

`backend/app/engine/ai_gate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

from ..core.config import settings

Tranche = Literal["T0", "T1", "T2", "T3"]


@dataclass(frozen=True)
class GateDecision:
    ok: bool
    threshold: float
    p_win: float
    reason: str


def threshold_for_tranche(tranche: Tranche) -> float:
    if tranche == "T0":
        return float(settings.AI_GATE_T0)
    if tranche == "T1":
        return float(settings.AI_GATE_T1)
    if tranche == "T2":
        return float(settings.AI_GATE_T2)
    return float(settings.AI_GATE_T3)


def allow(p_win: float | None, tranche: Tranche) -> GateDecision:
    thr = float(threshold_for_tranche(tranche))
    if p_win is None:
        return GateDecision(ok=True, threshold=thr, p_win=0.0, reason="no_model")
    p = float(p_win)
    if p >= thr:
        return GateDecision(ok=True, threshold=thr, p_win=p, reason="ok")
    return GateDecision(ok=False, threshold=thr, p_win=p, reason="below_threshold")
```

- [ ] **Step 2: Tests**

`backend/tests/test_ai_gate.py`:

```python
import unittest
from app.engine.ai_gate import allow


class TestAIGate(unittest.TestCase):
    def test_allow_none_model(self):
        d = allow(None, "T0")
        self.assertTrue(d.ok)
        self.assertEqual(d.reason, "no_model")

    def test_blocks_below_threshold(self):
        d = allow(0.1, "T0")
        self.assertFalse(d.ok)
        self.assertEqual(d.reason, "below_threshold")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/ai_gate.py backend/tests/test_ai_gate.py
git commit -m "feat(ai): add tranche-based ai gate"
```

---

### Task 5: Brain interface + brains iniciales

**Files:**
- Create: `backend/app/engine/brains/types.py`
- Create: `backend/app/engine/brains/*.py`
- Create: `backend/app/engine/multi_brain.py`
- Test: `backend/tests/test_multi_brain_signal.py`

- [ ] **Step 1: Definir tipos comunes**

`backend/app/engine/brains/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

Direction = Literal["buy", "sell", "neutral"]
BrainId = Literal["trend", "pullback", "breakout", "mean_reversion"]


@dataclass(frozen=True)
class BrainContext:
    symbol: str
    provider: str
    base_timeframe: str
    csv_path: str | None
    frames: List[Dict[str, Any]]
    analysis: Dict[str, Any]


@dataclass(frozen=True)
class BrainSignal:
    brain: BrainId
    direction: Direction
    confidence: float
    opportunity_score: float
    reasons: List[str]
    risk: Dict[str, Any]
    ai_p_win: float | None = None
```

- [ ] **Step 2: Implementar brains como “post-procesadores”**

Idea del MVP: reutilizar `NairaEngine.analyze()` para construir `analysis` base y luego cada brain:
- valida setup (entry_rules) usando el dataframe base con features
- si no hay setup: baja score/conf o marca neutral con reason

Crear:
- `backend/app/engine/brains/trend.py`
- `backend/app/engine/brains/pullback.py`
- `backend/app/engine/brains/breakout.py`
- `backend/app/engine/brains/mean_reversion.py`

Cada uno expone `run(ctx: BrainContext) -> BrainSignal`.

- [ ] **Step 3: Orquestador multi-brain**

`backend/app/engine/multi_brain.py`:
- usa `RegimeRouter` para elegir brains
- ejecuta dominante (+ secundario si aplica)
- combina con `Aggregator` (Task 6)
- aplica `AI Gate` (Task 4) antes de devolver señal final (en señales/scan)

- [ ] **Step 4: Test básico del pipeline (sin datos externos)**

`backend/tests/test_multi_brain_signal.py`:
- construye `frames` sintéticos para forzar régimen trend/range
- valida que `multi_brain` devuelve brain esperado y que reasons incluye “regime=…”

- [ ] **Step 5: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/brains backend/app/engine/multi_brain.py backend/tests/test_multi_brain_signal.py
git commit -m "feat(brains): add multi-brain orchestration and initial brains"
```

---

### Task 6: Aggregator (ensemble controlado) + tests

**Files:**
- Create: `backend/app/engine/ensemble.py`
- Test: `backend/tests/test_ensemble.py`

- [ ] **Step 1: Implementar agregador**

`backend/app/engine/ensemble.py`:
- entrada: `BrainSignal dominant`, `BrainSignal | None secondary`
- reglas:
  - dirección final = dominante
  - si secundario coincide, +bonus de confianza
  - si contradice, -penalización y añadir reason
  - cap de confidence 0..1 y score 0..100

- [ ] **Step 2: Tests de conflicto**

`backend/tests/test_ensemble.py`:
- caso agreement: confidence sube
- caso conflict: confidence baja y reason contiene “disagree”

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/ensemble.py backend/tests/test_ensemble.py
git commit -m "feat(ensemble): add controlled ensemble aggregator"
```

---

### Task 7: Integración en API (/signal y /scan) + scanner_service

**Files:**
- Modify: `backend/app/api/v1/endpoints/naira.py`
- Modify: `backend/app/services/scanner_service.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Extender /signal**

En `GET /api/v1/naira/signal`:
- añadir query:
  - `mode=single|multi` (default single)
  - `balance_usdt` (optional; si no se pasa, usa `settings.BALANCE_USDT`)
  - `asset=crypto|fx|metals` (optional; si no se pasa, inferir por símbolo)
- si `mode=multi`, usar `MultiBrainOrchestrator` y aplicar AI gate.

- [ ] **Step 2: Extender /scan**

En `GET /api/v1/naira/scan`:
- si `symbols` está vacío:
  - construir universo con `UniverseManager` usando `asset` y `balance_usdt`
- scan por etapas (MVP):
  - ejecutar analyze base para estructura
  - sólo para top candidatos (por score base) ejecutar multi-brain completo

- [ ] **Step 3: ScannerService**

En `scanner_service.scan_once()`:
- reemplazar `watchlist.load()` por:
  - si hay watchlist explícita: usarla
  - si no: universo por asset+balance desde settings
- guardar en alerta el `brain` y `regime` usados

- [ ] **Step 4: Tests API**

Extender `backend/tests/test_api.py`:
- añadir llamada a `/api/v1/naira/signal?mode=multi&symbol=TEST&provider=csv&base_timeframe=1h`
- assert status 200 y que respuesta incluye `direction` y `risk`

- [ ] **Step 5: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/naira.py backend/app/services/scanner_service.py backend/tests/test_api.py
git commit -m "feat(api): add multi mode + tranche-based universe scan"
```

---

### Task 8: Backtesting multi-brain (fase 1 completa)

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Modify: `backend/app/api/v1/endpoints/naira.py`
- Test: `backend/tests/test_engine.py`

- [ ] **Step 1: Añadir `strategy_mode` a NairaConfig**

En `NairaConfig`:

```python
strategy_mode: str = "single"  # single | multi
```

- [ ] **Step 2: Integrar multi-brain en backtest**

En el loop de backtest (donde se decide entrada):
- si `strategy_mode == "multi"`:
  - llamar orquestador multi-brain con los frames actuales
  - elegir `entry_kind` según brain dominante (trend/pullback/breakout/mr)
  - aplicar AI gate para aceptar entrada

- [ ] **Step 3: Exponer en endpoint /backtest**

En `POST /api/v1/naira/backtest`:
- aceptar `strategy_mode` en payload
- pasar a `NairaConfig` override

- [ ] **Step 4: Tests**

En `backend/tests/test_engine.py`:
- ejecutar `backtest(..., config={"strategy_mode":"multi"})` con `provider=csv` y assert que no rompe y devuelve metrics/trades.

- [ ] **Step 5: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/naira_engine.py backend/app/api/v1/endpoints/naira.py backend/tests/test_engine.py
git commit -m "feat(backtest): add multi-brain strategy mode"
```

---

### Task 9: Docs + operación

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Documentar variables nuevas**

Actualizar `.env.example` y `README.md` con:
- `BALANCE_USDT`
- `CRYPTO_T0_MAX/CRYPTO_T1_MAX/CRYPTO_T2_MAX`
- `FX_T0_MAX/FX_T1_MAX/FX_T2_MAX`
- `AI_GATE_T0..AI_GATE_T3`
- `mode=multi` y `strategy_mode=multi`

- [ ] **Step 2: Smoke run**

Run:
```bash
cd /workspace
PYENV_VERSION=3.12.13 python -m pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --port 8000
```
Expected: server up, then:
`curl -sS 'http://localhost:8000/api/v1/naira/signal?symbol=TEST&provider=csv&base_timeframe=1h&mode=multi'`

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document multi-brain and market scaling config"
```

---

## Auto-revisión del plan

- Cobertura de spec: universo por tramo+asset, router por régimen, brains iniciales, AI gate, agregador, integración API/scanner y backtest.
- Placeholder scan: sin marcadores pendientes.
- Consistencia de nombres: tramos `T0..T3`, brains `trend/pullback/breakout/mean_reversion`, modo `single|multi`.
