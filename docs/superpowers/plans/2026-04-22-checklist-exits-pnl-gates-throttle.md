# Checklist Tasks (Exits, PnL, Gates, Throttle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar tareas del checklist: (1) BE+lock+trailing sin conflicto, (2) PnL total incluyendo parciales, (3) contadores explicables de gates/no-entrada, (4) throttling/backoff en `data:update`.

**Architecture:** Cambios concentrados en `backend/app/engine/naira_engine.py` (gestión de salida, telemetría, parciales) y `scripts/tasks.py` (throttle en data update). Se añaden tests unitarios/integ para evitar regresiones.

**Tech Stack:** Python, pytest, pandas/numpy.

---

## Cambios de Archivos (mapa)

**Modificar:**
- `backend/app/engine/naira_engine.py`
- `backend/app/engine/execution_gates.py` (si es necesario para exponer motivos)
- `scripts/tasks.py`

**Crear/Modificar tests:**
- Create: `backend/tests/test_backtest_be_lock_trailing.py`
- Modify: `backend/tests/test_engine.py` (si hace falta)
- Create: `backend/tests/test_partial_pnl_total.py`

---

### Task 1: BE (1R) + Lock (1.5R, +0.1R) + Trailing (sin conflicto)

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Test: `backend/tests/test_backtest_be_lock_trailing.py`

- [ ] **Step 1: Escribir test (falla) de SL que nunca retrocede**

```python
import sys
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.naira_engine import NairaEngine, NairaConfig


def test_be_lock_trailing_never_decreases_sl_for_buy():
    with tempfile.TemporaryDirectory() as td:
        sym_dir = Path(td) / "history" / "csv" / "TEST"
        sym_dir.mkdir(parents=True, exist_ok=True)

        start = pd.Timestamp("2025-01-01T00:00:00Z")
        n = 220
        times = pd.date_range(start=start, periods=n, freq="1h")
        close = np.ones(n) * 100.0
        close[150:] = np.linspace(100.0, 105.0, num=n - 150)
        close[180:] = np.linspace(105.0, 101.0, num=n - 180)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        high = np.maximum(open_, close) + 0.5
        low = np.minimum(open_, close) - 0.5
        df = pd.DataFrame({"datetime": times, "open": open_, "high": high, "low": low, "close": close, "volume": 1000.0})
        df.to_csv(sym_dir / "1h.csv", index=False)

        cfg = NairaConfig(
            strategy_mode="multi",
            entry_mode="none",
            confirm_higher_tfs=False,
            timing_timeframe="",
            alignment_threshold=0.0,
            slope_threshold_pct=0.0,
            adx_threshold=0.0,
            min_confidence=0.0,
            be_trigger_r=1.0,
            trail_trigger_r=1.5,
            lock_r=0.10,
        )
        eng = NairaEngine(data_dir=str(td), config=cfg)
        r = eng.backtest(
            symbol="TEST",
            provider="csv",
            base_timeframe="1h",
            max_bars=220,
            apply_execution_gates=False,
        )
        trades = r.get("trades") or []
        assert len(trades) > 0
        t0 = trades[0]
        trail = (t0.get("sl_updates") or [])
        if not trail:
            return
        for i in range(1, len(trail)):
            assert float(trail[i]["sl"]) >= float(trail[i - 1]["sl"])
```

- [ ] **Step 2: Ejecutar test y verificar FAIL**

Run:

```bash
pytest -q backend/tests/test_backtest_be_lock_trailing.py
```

Expected: FAIL (campos/config inexistentes; no hay `sl_updates`).

- [ ] **Step 3: Implementar en `NairaConfig` y backtest**

1) En `NairaConfig` añadir campos (defaults):
- `be_trigger_r: float = 1.0`
- `trail_trigger_r: float = 1.5`
- `lock_r: float = 0.10`

2) En el loop de posición abierta:
- Calcular `R = abs(entry - sl_initial)` (persistir `sl_initial` al abrir).
- Si no `be_done` y se cumple be_trigger: `sl = entry`.
- Si movimiento >= trail_trigger:
  - `lock_sl = entry ± lock_r*R`
  - `trail_sl = price ± trailing_atr_mult*ATR`
  - Buy: `sl = max(sl, lock_sl, trail_sl)`
  - Sell: `sl = min(sl, lock_sl, trail_sl)`

3) (Debug opcional) Guardar `sl_updates` en trade (lista de dicts `{time, sl, reason}`) sólo si `include_debug=True` para no inflar reports.

- [ ] **Step 4: Ajustar test para validar sin `sl_updates` si no se activa debug**

Cambiar el test para:
- forzar `include_debug=True`, o
- validar que `pnl` no es 0 cuando hace lock (según dataset).

- [ ] **Step 5: Ejecutar test y suite**

Run:

```bash
pytest -q backend/tests/test_backtest_be_lock_trailing.py
pytest -q
```

Expected: PASS.

---

### Task 2: PnL total por trade incluyendo parciales

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Test: `backend/tests/test_partial_pnl_total.py`

- [ ] **Step 1: Escribir test (falla) de `pnl_total = pnl_final + sum(partials)`**

```python
import sys
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.naira_engine import NairaEngine, NairaConfig


def test_trade_pnl_total_includes_partials():
    with tempfile.TemporaryDirectory() as td:
        sym_dir = Path(td) / "history" / "csv" / "TEST"
        sym_dir.mkdir(parents=True, exist_ok=True)

        start = pd.Timestamp("2025-01-01T00:00:00Z")
        n = 400
        times = pd.date_range(start=start, periods=n, freq="1h")
        close = np.linspace(100.0, 120.0, num=n)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        high = np.maximum(open_, close) + 1.0
        low = np.minimum(open_, close) - 1.0
        df = pd.DataFrame({"datetime": times, "open": open_, "high": high, "low": low, "close": close, "volume": 1000.0})
        df.to_csv(sym_dir / "1h.csv", index=False)

        cfg = NairaConfig(
            strategy_mode="multi",
            entry_mode="none",
            confirm_higher_tfs=False,
            timing_timeframe="",
            alignment_threshold=0.0,
            slope_threshold_pct=0.0,
            adx_threshold=0.0,
            min_confidence=0.0,
            partial_1r_pct=0.5,
            partial_2r_pct=0.25,
        )
        eng = NairaEngine(data_dir=str(td), config=cfg)
        r = eng.backtest(symbol="TEST", provider="csv", base_timeframe="1h", max_bars=400, apply_execution_gates=False, include_debug=True)
        trades = r.get("trades") or []
        assert len(trades) > 0
        t0 = trades[0]
        partials = t0.get("partials") or []
        pnl_total = float(t0.get("pnl_total") or 0.0)
        pnl_final = float(t0.get("pnl_final") or t0.get("pnl") or 0.0)
        partial_sum = sum(float(x.get("pnl") or 0.0) for x in partials)
        assert abs(pnl_total - (pnl_final + partial_sum)) < 1e-9
```

- [ ] **Step 2: Ejecutar test y verificar FAIL**

Run:

```bash
pytest -q backend/tests/test_partial_pnl_total.py
```

Expected: FAIL (campos no existen).

- [ ] **Step 3: Implementar tracking de parciales**

En el backtest:
- Cuando se ejecuta parcial, registrar evento en `partials[]` del trade abierto:
  - `{time, qty, price, pnl}`
- Guardar `pnl_partials_sum` acumulado.
- Al cerrar trade:
  - `trade["pnl_final"] = pnl_remanente`
  - `trade["pnl_total"] = pnl_partials_sum + pnl_final`
  - mantener `trade["pnl"]` como antes por compatibilidad (o igualar a `pnl_total` si prefieres; dejarlo explícito).

- [ ] **Step 4: Ejecutar tests**

Run:

```bash
pytest -q backend/tests/test_partial_pnl_total.py
pytest -q
```

Expected: PASS.

---

### Task 3: Explicabilidad de no-entrada por gates/reglas

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- (Opcional) Modify: `backend/app/engine/execution_gates.py`
- Test: `backend/tests/test_backtest_timing_gate.py` (extender) o nuevo test

- [ ] **Step 1: Definir contadores en `metrics`**

Añadir en `metrics`:
- `blocked_no_signal`
- `blocked_min_confidence`
- `blocked_higher_tf`
- `blocked_timing_gate`
- `blocked_structural_gate`
- `blocked_confluence_gate`
- `blocked_threshold_gate`
- `blocked_risk_stop`
- `blocked_ai` (si se usa filtrado)

- [ ] **Step 2: Incrementar un motivo principal por barra**

En la lógica de entrada (cuando `side is None`):
- Si no hay señal válida: `blocked_no_signal += 1`
- Si falla confirmación TF alto: `blocked_higher_tf += 1`
- Si gates bloquean:
  - `timing_gate` → `blocked_timing_gate += 1`
  - `structural_gate` → `blocked_structural_gate += 1`
  - `confluence_gate` → `blocked_confluence_gate += 1`
  - `execution_threshold_gate` → `blocked_threshold_gate += 1`
- Si `block_new_trades` por risk stop: `blocked_risk_stop += 1`

- [ ] **Step 3: Test mínimo**

Usar un dataset pequeño y `apply_execution_gates=True` para asegurar que `blocked_timing_gate > 0` en el test de timing gate existente, o crear un test que valide que estos contadores existen en `metrics`.

- [ ] **Step 4: Ejecutar suite**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 4: Throttle/backoff en `data:update`

**Files:**
- Modify: `scripts/tasks.py`

- [ ] **Step 1: Añadir parámetros CLI/env**

En `build_parser()` añadir:
- `--update-min-sleep-ms` (default: 0)
- `--update-backoff-ms` (default: 250)
- `--update-max-retries` (default: 3)

- [ ] **Step 2: Aplicar throttle en `_update_one`**

En `_update_one`:
- `time.sleep(update_min_sleep_ms/1000)` antes de cada request a provider.
- En excepción, reintentar con backoff incremental (`update_backoff_ms * (attempt+1)`), hasta `update_max_retries`.

- [ ] **Step 3: Validación smoke**

Run:

```bash
python scripts/tasks.py data:update --provider binance --update-workers 2 --update-min-sleep-ms 50 --update-max-retries 2
```

Expected: se completa sin explotar en rate limit; si hay errores, quedan reflejados en `data_update.json`.

- [ ] **Step 4: Ejecutar suite**

Run:

```bash
pytest -q
```

Expected: PASS.

