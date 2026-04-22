# Timing Modes (EXPANSIÓN) + Entry Kind + Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir gate de timing (expansion/continuation) aplicado en señales y backtests, exponer `entry_kind` de forma consistente, y crear analyzer de resultados para `scan_job` y `random_backtests`.

**Architecture:** Extender `execution_gates.py` con `timing_gate`, añadir `TIMING_MODE` en settings. Integrar gate y `entry_kind` en `multi_brain` y `naira_engine`. Añadir `scripts/analyze_runs.py` y tests.

**Tech Stack:** Python, argparse, json, pandas (ya en repo), tests pytest/unittest.

---

## Mapa de cambios (archivos)

**Crear**
- `backend/app/engine/timing.py`
- `scripts/analyze_runs.py`
- `backend/tests/test_timing_gate.py`
- `backend/tests/test_analyze_runs.py`

**Modificar**
- `backend/app/core/config.py`
- `.env.example`
- `backend/app/engine/execution_gates.py`
- `backend/app/engine/naira_engine.py`
- `backend/app/engine/multi_brain.py`
- `backend/app/engine/entry_rules.py`
- `README.md`

---

### Task 1: Configuración de TIMING_MODE y thresholds

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Añadir settings**

En `backend/app/core/config.py` agregar:

```python
TIMING_MODE: str = _env("TIMING_MODE", "expansion").strip().lower()
EXPANSION_MAX_TREND_AGE: int = _env_int("EXPANSION_MAX_TREND_AGE", 2)
EXPANSION_MAX_EMA_COMPRESSION: float = float(_env("EXPANSION_MAX_EMA_COMPRESSION", "1.5"))
CONTINUATION_MAX_TREND_AGE: int = _env_int("CONTINUATION_MAX_TREND_AGE", 8)
CONTINUATION_MAX_EMA_COMPRESSION: float = float(_env("CONTINUATION_MAX_EMA_COMPRESSION", "5.0"))
```

- [ ] **Step 2: `.env.example`**

Agregar:

```env
TIMING_MODE=expansion
EXPANSION_MAX_TREND_AGE=2
EXPANSION_MAX_EMA_COMPRESSION=1.5
CONTINUATION_MAX_TREND_AGE=8
CONTINUATION_MAX_EMA_COMPRESSION=5.0
```

- [ ] **Step 3: README**

Documentar variables y significado.

---

### Task 2: Implementar `timing_gate` y cálculo de trend_age (señales)

**Files:**
- Create: `backend/app/engine/timing.py`
- Modify: `backend/app/engine/execution_gates.py`
- Test: `backend/tests/test_timing_gate.py`

- [ ] **Step 1: Crear `timing.py`**

Crear `backend/app/engine/timing.py`:

```python
from __future__ import annotations

from typing import List


def trend_age_bars_from_directions(dirs: List[str]) -> int:
    if not dirs:
        return 0
    last = str(dirs[-1] or "neutral")
    if last == "neutral":
        return 0
    run = 0
    for d in reversed(dirs):
        if str(d or "neutral") != last:
            break
        run += 1
    return int(run)
```

- [ ] **Step 2: Extender `execution_gates.py`**

Agregar al final:

```python
def timing_gate(trend_age_bars: int, ema_compression: float) -> GateResult:
    mode = str(settings.TIMING_MODE or "expansion").lower()
    if mode == "continuation":
        max_age = int(settings.CONTINUATION_MAX_TREND_AGE)
        max_comp = float(settings.CONTINUATION_MAX_EMA_COMPRESSION)
    else:
        max_age = int(settings.EXPANSION_MAX_TREND_AGE)
        max_comp = float(settings.EXPANSION_MAX_EMA_COMPRESSION)
    reasons = []
    if int(trend_age_bars) > int(max_age):
        reasons.append("gate_timing_age")
    if float(ema_compression) > float(max_comp):
        reasons.append("gate_timing_compression")
    ok = len(reasons) == 0
    return GateResult(ok=bool(ok), reasons=reasons, debug={"timing_mode": mode, "trend_age_bars": int(trend_age_bars), "ema_compression": float(ema_compression), "max_trend_age": int(max_age), "max_ema_compression": float(max_comp)})
```

- [ ] **Step 3: Test**

Crear `backend/tests/test_timing_gate.py`:

```python
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.execution_gates import timing_gate


class TestTimingGate(unittest.TestCase):
    def test_expansion_blocks(self):
        d = timing_gate(trend_age_bars=3, ema_compression=1.0)
        self.assertFalse(d.ok)
        self.assertIn("gate_timing_age", d.reasons)

    def test_expansion_blocks_compression(self):
        d = timing_gate(trend_age_bars=1, ema_compression=2.0)
        self.assertFalse(d.ok)
        self.assertIn("gate_timing_compression", d.reasons)


if __name__ == "__main__":
    unittest.main()
```

---

### Task 3: Exponer `trend_age_bars` en analyze (frames base)

**Files:**
- Modify: `backend/app/engine/naira_engine.py`

- [ ] **Step 1: Añadir `trend_age_bars` al frame base**

En el punto donde `analyze` construye `frames`, añadir:
- una lista `dirs` de los últimos N `direction` del frame base
- `trend_age = trend_age_bars_from_directions(dirs)`
- incluir `trend_age_bars` en el frame del `base_timeframe`

---

### Task 4: Integrar timing gate + entry_kind en `multi_brain`

**Files:**
- Modify: `backend/app/engine/multi_brain.py`
- Modify: `backend/app/engine/brains/*.py`
- Modify: `backend/app/engine/entry_rules.py`

- [ ] **Step 1: Ejecutar timing gate**

En `multi_brain.run_multi_brain(...)`, después de `frames`:
- obtener `trend_age_bars` y `ema_compression` del frame base (fallback 0)
- llamar `timing_gate(...)`
- si falla → neutral + reasons + debug

- [ ] **Step 2: Rellenar `entry_kind`**

Definir una regla:
- `trend/pullback` → `decide_entry(..., mode="hybrid")` y usar `ed.kind`
- `breakout` → `break_retest`
- `mean_reversion` → `mean_reversion`

Incluir `entry_kind` en la salida `merged`.

- [ ] **Step 3: Tests smoke**

Añadir test o ampliar `test_multi_brain_signal.py` verificando que `entry_kind` existe cuando `direction != neutral`.

---

### Task 5: Integrar timing gate en backtest (NO ENTRAR)

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Modify: `backend/tests/test_engine.py`

- [ ] **Step 1: Gate por timing en backtest**

En el loop de entrada:
- usar `trend_age_arr[i]` y `comp_arr[i]`
- si `timing_gate(...)` falla → `continue`

- [ ] **Step 2: Test**

Crear un test que construye un csv con compresión alta y verifica `len(trades)==0` cuando `TIMING_MODE=expansion`.

---

### Task 6: Script analyzer `scripts/analyze_runs.py`

**Files:**
- Create: `scripts/analyze_runs.py`
- Test: `backend/tests/test_analyze_runs.py`

- [ ] **Step 1: Implementar parser y métricas**

`scripts/analyze_runs.py` (argparse):
- `--scan-json`
- `--random-jsonl`
- `--out-md`
- `--out-json`

Métricas mínimas:
- scan: top por `opportunity_score`, conteo por `direction`, bucket por `trend_age_bars` y `ema_compression`
- random: leer `metrics`, extraer `expectancy` si existe o derivarlo con `net_pnl / max(1, trades)` cuando existan campos

- [ ] **Step 2: Test**

Crear fixtures temporales con JSON mínimo y validar que genera markdown.

---

### Task 7: Verificación

- [ ] Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`
- [ ] Run (manual): `PYENV_VERSION=3.12.13 python scripts/scan_job.py --provider csv --base_timeframe 1h --symbols BTCUSDT,ETHUSDT --top 5 > /tmp/scan.json`
- [ ] Run (manual): `PYENV_VERSION=3.12.13 python scripts/analyze_runs.py --scan-json /tmp/scan.json --out-md /tmp/report.md`

