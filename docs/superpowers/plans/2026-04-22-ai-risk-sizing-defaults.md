# AI Risk Sizing Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que el pipeline use `ai_risk` por defecto (1–5%), con fallback a `fixed_risk` al 2% cuando no exista modelo (`ai_prob_entry is None`), y registrar `risk_pct_used`/`sizing_mode_used` en cada trade.

**Architecture:** Se ajusta `NairaEngine.backtest` para que el modo `ai_risk` compute `risk_pct_used` desde `ai_prob_entry` y, si no hay AI, degrade a `fixed_risk` con `risk_per_trade_pct=2.0`. El pipeline (`scripts/tasks.py`) pasa defaults de sizing por CLI/env y guarda en cada trade el sizing efectivo usado.

**Tech Stack:** Python, numpy/pandas, pytest.

---

## Cambios de Archivos (mapa)

**Modificar:**
- `backend/app/engine/naira_engine.py`
- `scripts/tasks.py`

**Crear/Modificar tests:**
- Crear `backend/tests/test_ai_risk_fallback.py`

---

### Task 1: Test unitario del fallback `ai_risk -> fixed_risk (2%)`

**Files:**
- Create: `backend/tests/test_ai_risk_fallback.py`

- [ ] **Step 1: Escribir test (falla) que verifica `risk_pct_used` y `sizing_mode_used`**

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine, NairaConfig


def test_ai_risk_falls_back_to_fixed_risk_when_no_model():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.backtest(
        symbol="TEST",
        provider="csv",
        base_timeframe="1h",
        max_bars=1200,
        sizing_mode="ai_risk",
        risk_per_trade_pct=2.0,
        ai_assisted_sizing=True,
        ai_risk_min_pct=1.0,
        ai_risk_max_pct=5.0,
    )
    trades = r.get("trades") or []
    if not trades:
        return
    t0 = trades[0]
    meta = t0.get("entry_meta") or {}
    assert meta.get("sizing_mode_used") in ("fixed_risk_fallback", "fixed_risk")
    assert float(meta.get("risk_pct_used") or 0.0) == 2.0
```

- [ ] **Step 2: Ejecutar test y verificar FAIL**

Run:

```bash
pytest -q backend/tests/test_ai_risk_fallback.py
```

Expected: FAIL porque no existen esos campos aún (`sizing_mode_used`, `risk_pct_used`).

---

### Task 2: Implementar defaults de ai_risk y fallback en `NairaEngine.backtest`

**Files:**
- Modify: `backend/app/engine/naira_engine.py`

- [ ] **Step 1: Ajustar lógica de sizing para `ai_risk`**

En el bloque donde se calcula `ai_p_entry` y se decide `risk_pct` (zona `sm in (...)`), introducir:

- Si `sizing_mode == "ai_risk"` y `ai_p_entry is None`:
  - usar `risk_pct = risk_per_trade_pct` (default 2.0)
  - setear `sizing_mode_used = "fixed_risk_fallback"`
- Si `sizing_mode == "ai_risk"` y `ai_p_entry` existe:
  - `risk_pct = ai_risk_min_pct + (ai_risk_max_pct - ai_risk_min_pct) * ai_p_entry`
  - setear `sizing_mode_used = "ai_risk"`

- [ ] **Step 2: Guardar auditoría en `entry_meta`**

Al construir `entry_meta`, añadir:

```python
entry_meta["risk_pct_used"] = float(risk_pct_used)
entry_meta["sizing_mode_used"] = str(sizing_mode_used)
```

Y mantener `filled_qty` (ya existe) como la cantidad efectiva.

- [ ] **Step 3: Ejecutar test del Task 1**

Run:

```bash
pytest -q backend/tests/test_ai_risk_fallback.py
```

Expected: PASS (o skip implícito si no hay trades en el dataset TEST; si ocurre, ajustar el test para usar un símbolo/dataset de fixtures existente).

- [ ] **Step 4: Ejecutar suite completa**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 3: Hacer `ai_risk` default en pipeline (`scripts/tasks.py`)

**Files:**
- Modify: `scripts/tasks.py`

- [ ] **Step 1: Extender CLI/env con sizing params**

Agregar flags a `build_parser()`:

```python
sub.add_argument("--sizing-mode", default=os.getenv("PIPELINE_SIZING_MODE", "ai_risk"), choices=["fixed_qty", "fixed_risk", "ai_risk"])
sub.add_argument("--risk-per-trade-pct", type=float, default=float(os.getenv("PIPELINE_RISK_PCT", "2.0") or "2.0"))
sub.add_argument("--ai-risk-min-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MIN_PCT", "1.0") or "1.0"))
sub.add_argument("--ai-risk-max-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MAX_PCT", "5.0") or "5.0"))
sub.add_argument("--max-leverage", type=float, default=float(os.getenv("PIPELINE_MAX_LEVERAGE", "1.0") or "1.0"))
```

- [ ] **Step 2: Pasar parámetros a backtest**

En `_bt_one` dentro de `cmd_backtest_top/cmd_backtest_global`, llamar:

```python
r = eng.backtest(
    ...,
    sizing_mode=str(sizing_mode),
    risk_per_trade_pct=float(risk_per_trade_pct),
    ai_assisted_sizing=True,
    ai_risk_min_pct=float(ai_risk_min_pct),
    ai_risk_max_pct=float(ai_risk_max_pct),
    max_leverage=float(max_leverage),
)
```

- [ ] **Step 3: Smoke test del pipeline**

Run:

```bash
python scripts/tasks.py backtest:top --provider binance --sizing-mode ai_risk --risk-per-trade-pct 2 --ai-risk-min-pct 1 --ai-risk-max-pct 5
```

Expected:
- Los `filled_qty` sean significativamente mayores que 1 en activos baratos cuando el SL sea razonable.
- `entry_meta` contenga `risk_pct_used` y `sizing_mode_used`.

- [ ] **Step 4: Ejecutar suite**

Run:

```bash
pytest -q
```

Expected: PASS.

