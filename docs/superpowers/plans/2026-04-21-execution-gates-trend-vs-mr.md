# Execution Gates + Trend vs Mean Reversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar gates de ejecución (estructura, confluencia, umbrales) y separar Trend vs Mean Reversion de forma consistente en señales/scan y backtests.

**Architecture:** Centralizar la lógica de gating en un módulo único (`execution_gates.py`) consumido por `multi_brain` y por `naira_engine` (backtest). Mantener reasons estables para auditoría.

**Tech Stack:** Python, pandas/numpy, FastAPI, tests pytest/unittest.

---

## Mapa de cambios (archivos)

**Crear**
- `backend/app/engine/execution_gates.py`
- `backend/tests/test_execution_gates.py`

**Modificar**
- `backend/app/core/config.py`
- `backend/app/engine/multi_brain.py`
- `backend/app/engine/brains/trend.py`
- `backend/app/engine/brains/mean_reversion.py`
- `backend/app/engine/naira_engine.py`
- `.env.example`
- `README.md`

---

### Task 1: Configuración de thresholds (settings)

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_execution_gates.py`

- [ ] **Step 1: Añadir settings de gates**

En `backend/app/core/config.py` agregar:

```python
STRUCT_ALIGN_4H_MIN: float = float(_env("STRUCT_ALIGN_4H_MIN", "0.6"))
STRUCT_ALIGN_1D_MIN: float = float(_env("STRUCT_ALIGN_1D_MIN", "0.6"))
CONFLUENCE_MIN: float = float(_env("CONFLUENCE_MIN", "0.2"))
EXEC_CONF_MIN: float = float(_env("EXEC_CONF_MIN", "0.65"))
EXEC_ALIGN_MIN: float = float(_env("EXEC_ALIGN_MIN", "0.7"))

MR_SPREAD_FAST_PCT_MIN: float = float(_env("MR_SPREAD_FAST_PCT_MIN", "1.0"))
MR_REQUIRE_OPPOSITE_CURVATURE: int = _env_int("MR_REQUIRE_OPPOSITE_CURVATURE", 1)
```

- [ ] **Step 2: Añadirlos a `.env.example`**

```env
STRUCT_ALIGN_4H_MIN=0.6
STRUCT_ALIGN_1D_MIN=0.6
CONFLUENCE_MIN=0.2
EXEC_CONF_MIN=0.65
EXEC_ALIGN_MIN=0.7
MR_SPREAD_FAST_PCT_MIN=1.0
MR_REQUIRE_OPPOSITE_CURVATURE=1
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 2: Módulo común `execution_gates.py`

**Files:**
- Create: `backend/app/engine/execution_gates.py`
- Test: `backend/tests/test_execution_gates.py`

- [ ] **Step 1: Crear tipos y helpers**

Crear `backend/app/engine/execution_gates.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reasons: List[str]
    debug: Dict[str, Any]


def _frames_by_tf(frames: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in frames or []:
        tf = str(f.get("timeframe") or "")
        if tf:
            out[tf] = dict(f)
    return out


def structural_gate(frames: List[Dict[str, Any]]) -> GateResult:
    by_tf = _frames_by_tf(frames)
    a4 = float((by_tf.get("4h") or {}).get("alignment") or 0.0)
    a1 = float((by_tf.get("1d") or {}).get("alignment") or 0.0)
    ok = not (a4 < float(settings.STRUCT_ALIGN_4H_MIN) and a1 < float(settings.STRUCT_ALIGN_1D_MIN))
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_structural"]), debug={"alignment_4h": a4, "alignment_1d": a1})


def confluence_gate(frames: List[Dict[str, Any]], base_timeframe: str) -> GateResult:
    by_tf = _frames_by_tf(frames)
    f = by_tf.get(str(base_timeframe)) or by_tf.get("4h") or {}
    lv = float(f.get("level_confluence_score") or 0.0)
    ok = lv >= float(settings.CONFLUENCE_MIN)
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_low_confluence"]), debug={"level_confluence_score": lv})


def execution_threshold_gate(frames: List[Dict[str, Any]], base_timeframe: str) -> GateResult:
    by_tf = _frames_by_tf(frames)
    f = by_tf.get(str(base_timeframe)) or {}
    conf = float(f.get("confidence") or 0.0)
    ali = float(f.get("alignment") or 0.0)
    ok = (conf >= float(settings.EXEC_CONF_MIN)) and (ali >= float(settings.EXEC_ALIGN_MIN))
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_execution_threshold"]), debug={"exec_conf": conf, "exec_align": ali})
```

- [ ] **Step 2: Test unitarios**

Crear `backend/tests/test_execution_gates.py`:

```python
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.execution_gates import structural_gate, confluence_gate, execution_threshold_gate


class TestExecutionGates(unittest.TestCase):
    def test_structural_gate_blocks(self):
        frames = [
            {"timeframe": "4h", "alignment": 0.5},
            {"timeframe": "1d", "alignment": 0.5},
        ]
        r = structural_gate(frames)
        self.assertFalse(r.ok)
        self.assertIn("gate_structural", r.reasons)

    def test_confluence_gate_blocks(self):
        frames = [{"timeframe": "1h", "level_confluence_score": 0.1}]
        r = confluence_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_low_confluence", r.reasons)

    def test_exec_threshold_blocks(self):
        frames = [{"timeframe": "1h", "confidence": 0.6, "alignment": 0.6}]
        r = execution_threshold_gate(frames, base_timeframe="1h")
        self.assertFalse(r.ok)
        self.assertIn("gate_execution_threshold", r.reasons)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 3: Aplicar gates en `multi_brain` (signal/scan/scanner)

**Files:**
- Modify: `backend/app/engine/multi_brain.py`

- [ ] **Step 1: Evaluar gates antes del brain**

En `run_multi_brain(...)`:
- calcular:
  - `structural_gate(frames)`
  - `confluence_gate(frames, base_timeframe)`
  - `execution_threshold_gate(frames, base_timeframe)`
- si cualquier gate falla: devolver `direction=neutral`, score 0, reasons agregadas.

- [ ] **Step 2: Incluir valores en debug si include_debug=true**

Añadir a `debug`:
- `gates`: dict con debug de cada gate y reasons.

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 4: Separación Trend vs MR (requisitos mínimos por brain)

**Files:**
- Modify: `backend/app/engine/brains/trend.py`
- Modify: `backend/app/engine/brains/mean_reversion.py`

- [ ] **Step 1: Trend requiere 1W+1D alineados**

En `trend.run(ctx)`:
- leer `ctx.frames` y validar:
  - `direction` de `1d` y `1w` (si existe) coinciden con `analysis.direction`
  - `alignment` de `1d/1w` >= 0.7
- si no: devolver neutral + reason `trend_requirements_failed`

- [ ] **Step 2: MR requiere spread extremo + curvatura opuesta**

En `mean_reversion.run(ctx)`:
- usar `ctx.df_feat_base.iloc[-1]`:
  - `ema_spread_fast_pct`
  - `curvature`
- bloquear si:
  - `abs(ema_spread_fast_pct) < MR_SPREAD_FAST_PCT_MIN`
  - y/o si `MR_REQUIRE_OPPOSITE_CURVATURE=1` y la curvatura no confirma

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 5: Aplicar gates en backtest (NO ENTRAR)

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Test: `backend/tests/test_engine.py`

- [ ] **Step 1: Construir snapshot mínimo para gates dentro del loop**

En el loop principal de `backtest`:
- construir `frames_min` con:
  - `{"timeframe": base_timeframe, "confidence": base_conf, "alignment": alignment_base, "level_confluence_score": level_conf_base}`
  - `{"timeframe": "4h", "alignment": ...}`
  - `{"timeframe": "1d", "alignment": ...}`
- aplicar los 3 gates y si falla cualquiera: `continue`.

- [ ] **Step 2: Test**

Añadir test que fuerza confluence baja (mock simple con dataframe sintético) y verifica que no entra.

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 6: Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Documentar variables nuevas**

Agregar sección de “execution gates” y cómo afectan modo multi/backtest.

- [ ] **Step 2: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

## Auto-revisión del plan

- Cobertura: gates aplicados en multi (API/scan/scanner) y en backtest (skip entry).
- Sin placeholders.
- Reasons estables: `gate_structural`, `gate_low_confluence`, `gate_execution_threshold`.

