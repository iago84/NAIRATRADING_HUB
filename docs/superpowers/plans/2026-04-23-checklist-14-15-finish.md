# Checklist 14–15 Finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar las secciones 14–15 del checklist implementando: auditoría de sizing en `entry_meta`, métricas `pnl_partials`/`pnl_total`, mejoras de reporte HTML (datasets/backtests + timing gate), y mejoras 15 (lock/trailing coordinado, explicabilidad gates, throttling/backoff, portfolio backtest).

**Architecture:** Implementación incremental en 2 entregas. Entrega 1 cierra trazabilidad/observabilidad del pipeline (artefactos + métricas). Entrega 2 agrega mejoras de comportamiento (salidas, throttling, portfolio) con tests de regresión.

**Tech Stack:** Python, pytest, FastAPI (endpoints existentes), motor `backend/app/engine/naira_engine.py`, scripts `scripts/tasks.py` + `scripts/analyze_runs.py`.

---

## Pre-Flight: Preparar rama de trabajo

### Task 0: Rama limpia para cambios

**Files:**
- No code changes

- [ ] **Step 1: Crear rama**

Run:

```bash
git switch -c feat/checklist-14-15-finish
```

- [ ] **Step 2: Verificar árbol limpio**

Run:

```bash
git status -sb
```

Expected: sin conflictos, sin merges pendientes.

---

# Entrega 1 (Checklist 14): Operativa + Debug

### Task 1: Auditoría de sizing en entry_meta (risk_pct_used, sizing_mode_used)

**Files:**
- Modify: [naira_engine.py](file:///workspace/backend/app/engine/naira_engine.py)
- Modify: [naira.py](file:///workspace/backend/app/schemas/naira.py)
- Test: `backend/tests/test_entry_meta_sizing_audit.py` (nuevo)

- [ ] **Step 1: Escribir test que falla**

Create `backend/tests/test_entry_meta_sizing_audit.py`:

```python
import json
from backend.app.engine.naira_engine import NairaEngine, NairaConfig
from backend.app.core.config import settings


def test_entry_meta_contains_sizing_audit_fields():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.backtest(
        symbol="TEST",
        provider="csv",
        base_timeframe="15m",
        max_bars=200,
        sizing_mode="fixed_risk",
        risk_per_trade_pct=2.0,
        max_leverage=1.0,
        ai_assisted_sizing=False,
    )
    trades = r.get("trades") or []
    assert trades, "expected at least one trade in csv fixture"
    em = (trades[0].get("entry_meta") or {})
    assert "risk_pct_used" in em
    assert "sizing_mode_used" in em
```

Run:

```bash
pytest -q backend/tests/test_entry_meta_sizing_audit.py -k entry_meta
```

Expected: FAIL (campos no existen todavía).

- [ ] **Step 2: Implementar campos en el motor**

Modificar en `NairaEngine.backtest()` el lugar donde se arma `entry_meta` (actualmente incluye `ai_prob_entry`, `filled_qty`, etc.):

```python
entry_meta["risk_pct_used"] = float(risk_pct_used)
entry_meta["sizing_mode_used"] = str(sizing_mode_used)
```

Reglas:
- Si `sizing_mode == "ai_risk"` y se cae a sizing de riesgo fijo, usar `sizing_mode_used = "fixed_risk_fallback"`.
- En caso contrario, `sizing_mode_used` debe reflejar el modo efectivo (`fixed_risk`, `fixed_qty`, `ai_risk`, etc.).

- [ ] **Step 3: Alinear schema de trade**

En `backend/app/schemas/naira.py`, permitir que `entry_meta` incluya estos campos (si está tipado estricto). Mantener compatibilidad: no hacer campos requeridos globales si el schema ya admite dict libre.

- [ ] **Step 4: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_entry_meta_sizing_audit.py -k entry_meta
```

Expected: PASS.

---

### Task 2: Guardar pnl_partials y pnl_total por trade (sin romper compatibilidad)

**Files:**
- Modify: [naira_engine.py](file:///workspace/backend/app/engine/naira_engine.py)
- Test: `backend/tests/test_trade_partials_pnl_total.py` (nuevo)

- [ ] **Step 1: Escribir test que falla**

Create `backend/tests/test_trade_partials_pnl_total.py`:

```python
from backend.app.engine.naira_engine import NairaEngine, NairaConfig
from backend.app.core.config import settings


def test_trade_contains_pnl_partials_and_pnl_total():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.backtest(symbol="TEST", provider="csv", base_timeframe="15m", max_bars=500)
    trades = r.get("trades") or []
    assert trades
    t = trades[0]
    assert "pnl_partials" in t
    assert "pnl_total" in t
    assert isinstance(t["pnl_partials"], list)
    assert abs(float(t["pnl_total"]) - (float(t["pnl"]) + sum(float(x) for x in t["pnl_partials"]))) < 1e-9
```

Run:

```bash
pytest -q backend/tests/test_trade_partials_pnl_total.py
```

Expected: FAIL.

- [ ] **Step 2: Capturar parciales en ambos caminos (magnifier y no magnifier)**

En la lógica donde se ejecutan parciales (p1/p2), mantener una lista por trade:

```python
pnl_partials: list[float] = []
```

Cuando se realiza parcial:
- calcular el pnl parcial exacto que ya se materializa vía `cash += ...`
- hacer `pnl_partials.append(float(partial_pnl))`

Ejemplo de cálculo típico (long):

```python
partial_pnl = (partial_exit - entry) * partial_qty
```

Nota: usar el `partial_qty` real antes de decrementar `qty`.

- [ ] **Step 3: Persistir pnl_partials y pnl_total en cada trade**

En el diccionario final de trade (donde hoy se guarda `"pnl": pnl`), añadir:

```python
"pnl_partials": list(pnl_partials),
"pnl_total": float(pnl) + float(sum(pnl_partials)),
```

Sin renombrar `pnl`.

- [ ] **Step 4: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_trade_partials_pnl_total.py
```

Expected: PASS.

---

### Task 3: Reporte HTML (setup_edge.html) con Datasets/Backtests + Timing Gate

**Files:**
- Modify: [analyze_runs.py](file:///workspace/scripts/analyze_runs.py)
- Test: `backend/tests/test_setup_edge_html_contains_sections.py` (nuevo, smoke)

- [ ] **Step 1: Escribir test smoke que falla**

Create `backend/tests/test_setup_edge_html_contains_sections.py`:

```python
import os
import tempfile
from scripts.analyze_runs import main as analyze_main


def test_setup_edge_html_contains_sections(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        out_html = os.path.join(d, "setup_edge.html")
        out_md = os.path.join(d, "setup_edge.md")
        out_json = os.path.join(d, "setup_edge.json")
        argv = [
            "analyze_runs.py",
            "--dataset-dir",
            "backend/data/datasets",
            "--backtest-json",
            "backend/data/reports/2026-04-22/run_220148/backtest_5m_BTCUSDT.json",
            "--out-html",
            out_html,
            "--out-md",
            out_md,
            "--out-json",
            out_json,
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = analyze_main()
        assert rc == 0
        html = open(out_html, "r", encoding="utf-8").read()
        assert "Datasets" in html
        assert "Backtests" in html
```

Run:

```bash
pytest -q backend/tests/test_setup_edge_html_contains_sections.py
```

Expected: FAIL si no se genera o no contiene secciones.

- [ ] **Step 2: Incluir “Timing gate” en HTML**

En `summarize_backtest_json()` añadir lectura de:
- `metrics.gates_timing_blocked`
- `late_entry_report.recommendations` (si existe)

Ejemplo:

```python
metrics = obj.get("metrics") or {}
out["gates_timing_blocked"] = metrics.get("gates_timing_blocked")
ler = obj.get("late_entry_report") or {}
out["late_entry_recommendations"] = ler.get("recommendations")
```

Y en el HTML, añadir una tabla/section de timing gate (por ejemplo: total bloqueos + top recomendaciones agregadas).

- [ ] **Step 3: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_setup_edge_html_contains_sections.py
```

Expected: PASS.

---

### Task 4: Validación de artefactos en scripts/tasks.py (all)

**Files:**
- Modify: [tasks.py](file:///workspace/scripts/tasks.py)
- Test: `backend/tests/test_tasks_all_help_has_flags.py` (nuevo)

- [ ] **Step 1: Test de flags/help**

Create `backend/tests/test_tasks_all_help_has_flags.py`:

```python
import subprocess
import sys


def test_tasks_all_help_has_leverage_sweep_flag():
    cp = subprocess.run([sys.executable, "scripts/tasks.py", "all", "--help"], capture_output=True, text=True)
    assert cp.returncode == 0
    assert "--leverage-sweep" in cp.stdout
```

Run:

```bash
pytest -q backend/tests/test_tasks_all_help_has_flags.py
```

Expected: PASS (regresión).

- [ ] **Step 2: Añadir checks de existencia tras etapas clave**

En `cmd_report_setup_edge` y/o al final de `all`, validar:

```python
assert os.path.exists(os.path.join(run_dir, "setup_edge.html"))
```

Y para el resto:

```python
required = ["datasets_manifest.json", "setup_edge.json", "setup_edge.md", "setup_edge.html"]
missing = [p for p in required if not os.path.exists(os.path.join(run_dir, p))]
if missing:
    raise SystemExit(f"missing artifacts: {missing}")
```

- [ ] **Step 3: Smoke run CSV (si existe dataset TEST)**

Run:

```bash
python scripts/tasks.py all --provider csv --workers 1 --update-workers 1 --leverage-sweep
```

Expected: exit code 0 y generación de artefactos en el run_dir.

---

### Task 5: Actualizar checklist sección 14 a “hecho” donde aplique

**Files:**
- Modify: [checklist.md](file:///workspace/checklist.md#L204-L225)

- [ ] **Step 1: Marcar como [x] lo implementado y verificable**

Cambiar a `[x]`:
- “Artefactos por run” (si `all` los verifica/genera)
- “Auditoría de sizing (por trade)”
- “TP negativo / PnL raro” (una vez exista `pnl_partials` + `pnl_total`)
- “Timing gate bloqueando demasiado” (si el reporte HTML expone métricas/recomendaciones)

- [ ] **Step 2: Mantener manual lo que dependa de Binance real**

Si no se puede ejecutar desde CI, dejar “Pipeline end-to-end (binance)” como `[ ]` pero con comando presente.

---

# Entrega 2 (Checklist 15): Mejoras Prioritarias

### Task 6: Lock de beneficios coordinado con BE y trailing

**Files:**
- Modify: [naira_engine.py](file:///workspace/backend/app/engine/naira_engine.py)
- Test: `backend/tests/test_exit_lock_does_not_conflict_with_trailing.py` (nuevo)

- [ ] **Step 1: Test que falla (lock eleva SL después de trigger)**

Create `backend/tests/test_exit_lock_does_not_conflict_with_trailing.py` (test unitario simple usando una función helper si existe; si no existe, test de integración con `provider=csv`):

```python
from backend.app.engine.naira_engine import NairaEngine, NairaConfig
from backend.app.core.config import settings


def test_lock_sets_sl_once_triggered():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.backtest(symbol="TEST", provider="csv", base_timeframe="15m", max_bars=800)
    trades = r.get("trades") or []
    assert trades
    t = trades[0]
    em = (t.get("exit_meta") or {})
    assert "lock_triggered" in em
```

Run:

```bash
pytest -q backend/tests/test_exit_lock_does_not_conflict_with_trailing.py
```

Expected: FAIL.

- [ ] **Step 2: Implementar lock en R**

En el bucle de gestión del trade (donde hoy existe BE y trailing):
- Definir R inicial: `R0 = abs(entry - initial_sl)` (antes de modificar sl).
- Si precio alcanza `entry + lock_trigger_r * R0` (long) / `entry - lock_trigger_r * R0` (short):
  - setear `sl = max(sl, entry + lock_r * R0)` (long)
  - setear `sl = min(sl, entry - lock_r * R0)` (short)
- Registrar en `exit_meta`:

```python
exit_meta["lock_triggered"] = True
exit_meta["lock_sl"] = float(sl)
```

- [ ] **Step 3: Definir precedencia explícita**

Orden recomendado por tick/bar:
1) actualizar BE (si aplica)
2) aplicar lock (si aplica)
3) aplicar trailing (si aplica)

- [ ] **Step 4: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_exit_lock_does_not_conflict_with_trailing.py
```

Expected: PASS.

---

### Task 7: Explicabilidad de no-entrada (contadores por gate/regla)

**Files:**
- Modify: [execution_gates.py](file:///workspace/backend/app/engine/execution_gates.py)
- Modify: [naira_engine.py](file:///workspace/backend/app/engine/naira_engine.py)
- Test: `backend/tests/test_gates_reason_counters_in_metrics.py` (nuevo)

- [ ] **Step 1: Test que falla**

Create `backend/tests/test_gates_reason_counters_in_metrics.py`:

```python
from backend.app.engine.naira_engine import NairaEngine, NairaConfig
from backend.app.core.config import settings


def test_metrics_contains_gate_reason_counts():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.backtest(symbol="TEST", provider="csv", base_timeframe="15m", max_bars=300)
    m = r.get("metrics") or {}
    assert "gate_reason_counts" in m
    assert isinstance(m["gate_reason_counts"], dict)
```

Run:

```bash
pytest -q backend/tests/test_gates_reason_counters_in_metrics.py
```

Expected: FAIL.

- [ ] **Step 2: Implementar reason strings en gates**

Cambiar `execution_gates.timing_gate()` para retornar (ok, reason) o levantar una estructura tipo:

```python
return False, "timing_age"
```

y ajustar el motor para contar en:

```python
gate_reason_counts[reason] = gate_reason_counts.get(reason, 0) + 1
```

- [ ] **Step 3: Persistir en metrics**

Al final del backtest:

```python
metrics["gate_reason_counts"] = dict(gate_reason_counts)
```

- [ ] **Step 4: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_gates_reason_counters_in_metrics.py
```

Expected: PASS.

---

### Task 8: Throttling/backoff configurable en data:update

**Files:**
- Modify: [tasks.py](file:///workspace/scripts/tasks.py#L137-L199)
- Test: `backend/tests/test_data_update_backoff_retry.py` (nuevo, unit con fake provider)

- [ ] **Step 1: Test que falla (retry)**

Create `backend/tests/test_data_update_backoff_retry.py`:

```python
import time


def test_backoff_retry_policy_is_applied(monkeypatch):
    calls = {"n": 0}

    def fake_get_ohlc(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("rate limit")
        return []

    monkeypatch.setattr("scripts.tasks.BinanceRestOHLCVProvider.get_ohlc", fake_get_ohlc)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    from scripts.tasks import _retry_get_ohlc

    out = _retry_get_ohlc(max_retries=3, backoff_ms=10, min_sleep_ms=0, fn=lambda: [])
    assert calls["n"] >= 1
    assert out == []
```

Run:

```bash
pytest -q backend/tests/test_data_update_backoff_retry.py
```

Expected: FAIL (helper no existe).

- [ ] **Step 2: Implementar helper de retry en scripts/tasks.py**

Añadir función:

```python
def _retry_get_ohlc(max_retries: int, backoff_ms: int, min_sleep_ms: int, fn):
    ...
```

Reglas:
- Ejecutar `fn()`, si falla y quedan retries, `sleep` con backoff (por ejemplo exponencial) y reintentar.
- Aplicar `min_sleep_ms` entre requests exitosas también.

- [ ] **Step 3: Añadir flags al parser**

Agregar flags para subcomandos que usan `data:update` y `all`:
- `--update-min-sleep-ms` (default 0)
- `--update-backoff-ms` (default 250)
- `--update-max-retries` (default 3)

- [ ] **Step 4: Integrar helper en cmd_data_update**

En el bucle que llama a `prov.get_ohlc(...)`, envolver la llamada con `_retry_get_ohlc(...)`.

- [ ] **Step 5: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_data_update_backoff_retry.py
```

Expected: PASS.

---

### Task 9: Portfolio backtest (equity/drawdown consistente)

**Files:**
- Modify: [naira_engine.py](file:///workspace/backend/app/engine/naira_engine.py#L2063-L2248)
- Test: `backend/tests/test_portfolio_backtest_drawdown_consistent.py` (nuevo)

- [ ] **Step 1: Test que falla**

Create `backend/tests/test_portfolio_backtest_drawdown_consistent.py`:

```python
from backend.app.engine.naira_engine import NairaEngine, NairaConfig
from backend.app.core.config import settings


def test_portfolio_backtest_drawdown_is_non_negative():
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode="hybrid"))
    r = eng.portfolio_backtest(provider="csv", symbols=["TEST"], base_timeframe="15m", max_bars=300)
    m = r.get("metrics") or {}
    dd = float(m.get("max_drawdown_pct") or 0.0)
    assert dd >= 0.0
```

Run:

```bash
pytest -q backend/tests/test_portfolio_backtest_drawdown_consistent.py
```

Expected: FAIL si hay signo incorrecto o métrica ausente.

- [ ] **Step 2: Corregir cálculo si es necesario**

Asegurar:
- drawdown pct reportado como número positivo (0..100).
- equity/peak tracking correcto.

- [ ] **Step 3: Re-ejecutar test**

Run:

```bash
pytest -q backend/tests/test_portfolio_backtest_drawdown_consistent.py
```

Expected: PASS.

---

### Task 10: Actualizar checklist sección 15 a “hecho”

**Files:**
- Modify: [checklist.md](file:///workspace/checklist.md#L226-L231)

- [ ] **Step 1: Marcar items como [x] cuando tests pasen**

Cambiar a `[x]`:
- BE + lock + trailing
- `pnl_partials` y `pnl_total`
- contadores por gates/reglas
- throttling/backoff
- portfolio backtest

---

## Verificación final

- [ ] **Step 1: Lint mínimo**

Run:

```bash
python -m py_compile scripts/tasks.py scripts/analyze_runs.py backend/app/engine/naira_engine.py
```

- [ ] **Step 2: Test suite relevante**

Run:

```bash
pytest -q backend/tests/test_entry_meta_sizing_audit.py \
  backend/tests/test_trade_partials_pnl_total.py \
  backend/tests/test_setup_edge_html_contains_sections.py \
  backend/tests/test_tasks_all_help_has_flags.py \
  backend/tests/test_gates_reason_counters_in_metrics.py \
  backend/tests/test_data_update_backoff_retry.py \
  backend/tests/test_portfolio_backtest_drawdown_consistent.py
```

- [ ] **Step 3: Generar patch para aplicar en otras copias**

Run:

```bash
git diff --binary > nairatrading_hub_checklist_14_15.patch
```

