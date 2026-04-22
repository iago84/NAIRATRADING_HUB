# Tasks.py + Checklist Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que `scripts/tasks.py` soporte flags de sizing/riesgo del checklist y que el pipeline `backtest:*` / `all` funcione sin variables/kwargs inexistentes, actualizando `checklist.md` para reflejar el estado real.

**Architecture:** Añadir flags al parser, propagarlos a `cmd_backtest_top/cmd_backtest_global`, y pasarlos a `NairaEngine.backtest()` (que ya soporta esos parámetros). Actualizar checklist para marcar como completado lo que queda realmente implementado.

**Tech Stack:** Python, argparse, motor existente `backend/app/engine/naira_engine.py`.

---

### Task 1: Añadir flags al CLI y definir defaults

**Files:**
- Modify: [tasks.py](file:///workspace/scripts/tasks.py#L517-L599)

- [ ] **Step 1: Añadir flags al parser**

Editar `build_parser()` para añadir:
- `--sizing-mode` (default: `ai_risk`)
- `--risk-per-trade-pct` (default: `2.0`)
- `--ai-risk-min-pct` (default: `1.0`)
- `--ai-risk-max-pct` (default: `5.0`)
- `--max-leverage` (default: `1.0`)

- [ ] **Step 2: Definir variables en main() desde args**

Editar `main()` para definir:
- `sizing_mode`
- `risk_per_trade_pct`
- `ai_risk_min_pct`
- `ai_risk_max_pct`
- `max_leverage`

y eliminar el uso implícito de variables no definidas.

- [ ] **Step 3: Validar parsing**

Run: `python scripts/tasks.py backtest:top --help`
Expected: Debe listar los nuevos flags.

---

### Task 2: Propagar sizing/riesgo a backtest y arreglar prints rotos

**Files:**
- Modify: [tasks.py](file:///workspace/scripts/tasks.py#L272-L409)

- [ ] **Step 1: Actualizar firmas**

Actualizar `cmd_backtest_top(...)` y `cmd_backtest_global(...)` para aceptar:
- `sizing_mode: str`
- `risk_per_trade_pct: float`
- `ai_risk_min_pct: float`
- `ai_risk_max_pct: float`
- `max_leverage: float`

- [ ] **Step 2: Pasar args a eng.backtest()**

Dentro de `_bt_one(...)`, pasar:
- `sizing_mode=...`
- `risk_per_trade_pct=...`
- `ai_risk_min_pct=...`
- `ai_risk_max_pct=...`
- `max_leverage=...`
- `ai_assisted_sizing=True` cuando `sizing_mode == "ai_risk"` (si no, False)

- [ ] **Step 3: Arreglar logs**

Reemplazar `print(... sizing_mode={sizing_mode})` por el parámetro real (sin variable global inexistente).

- [ ] **Step 4: Verificación básica**

Run: `python -m py_compile scripts/tasks.py`
Expected: Exit code 0.

---

### Task 3: Actualizar checklist para reflejar lo implementado

**Files:**
- Modify: [checklist.md](file:///workspace/checklist.md#L204-L231)

- [ ] **Step 1: Marcar como completado lo que ya está en el repo**

Marcar como `[x]`:
- “Flags clave del pipeline” (una vez que Task 1 esté hecho).
- “Datasets manifest: incluir rows + filtrar rows>0” (ya está implementado en `scripts/tasks.py`).

- [ ] **Step 2: Mantener pendientes lo no implementado en este cambio**

Mantener `[ ]`:
- Pipeline end-to-end (binance) (no se valida automáticamente aquí).
- Artefactos por run (si falta algo fuera de datasets manifest).
- Auditoría de sizing (si no está en `entry_meta` todavía).
- TP negativo / timing gate / mejoras 15 (si no se implementan ahora).

---

### Task 4: Smoke test del pipeline (opcional pero recomendado)

**Files:**
- No code changes (solo ejecución)

- [ ] **Step 1: Ejecutar help de all**

Run: `python scripts/tasks.py all --help`
Expected: Debe incluir flags nuevos.

- [ ] **Step 2: Ejecutar un subcomando no destructivo (si hay datos locales)**

Run: `python scripts/tasks.py scan --provider csv --workers 1 --update-workers 1`
Expected: Genera `data_update.json` y `scan_<tf>.json` en un run dir.

---

## Self-Review Checklist

- Sin variables no definidas (`sizing_mode`, etc.) en `scripts/tasks.py`.
- `cmd_backtest_top/global` aceptan y pasan parámetros de sizing/riesgo.
- `checklist.md` refleja exactamente lo implementado (sin marcar tareas no hechas).

