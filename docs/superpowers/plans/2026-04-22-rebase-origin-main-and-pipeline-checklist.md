# Rebase to origin/main + Pipeline Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebasar el trabajo para que esté basado en `origin/main`, consolidar el patch, mejorar el pipeline para que el manifest muestre datasets incluso con `rows=0`, y generar un `checklist.md` de mejoras/debug.

**Architecture:** Crear rama desde `origin/main`, aplicar patch consolidado (pipeline + risk stops + ai_risk + tests), ajustar `scripts/tasks.py` para que el manifest incluya conteo de filas por dataset (0 incluido), validar con `pytest -q`, y escribir `checklist.md` con recomendaciones operativas y de depuración.

**Tech Stack:** git, Python, pytest.

---

## Cambios de Archivos (mapa)

**Modificar:**
- `scripts/tasks.py`

**Crear/Modificar docs:**
- `checklist.md`

**Patch:**
- Generar `nairatrading_hub_consolidated.patch` contra `origin/main`

---

### Task 1: Rebasar el trabajo sobre `origin/main`

**Files:**
- N/A (operación git)

- [ ] **Step 1: Confirmar estado y actualizar refs**

Run:

```bash
git fetch origin --prune
git status -sb
git rev-list --left-right --count origin/main...HEAD
```

Expected: Ver si `HEAD` está ahead/behind y si hay cambios locales sin commitear.

- [ ] **Step 2: Crear rama nueva desde origin/main**

Run:

```bash
git switch -c trae/rebased-pipeline origin/main
```

Expected: Nueva rama basada exactamente en el tip de `origin/main`.

- [ ] **Step 3: Aplicar patch consolidado del trabajo previo**

Run:

```bash
git apply --index /workspace/pipeline_plus_ai_risk.patch
git apply --index /workspace/pipeline_backtest_concurrency_risk.patch
```

Expected: Aplicación limpia o conflictos (si hay conflictos, resolver y continuar).

- [ ] **Step 4: Verificar tests**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 2: Manifest de datasets incluye rows=0 (visible que “se intentó”)

**Files:**
- Modify: `scripts/tasks.py`

- [ ] **Step 1: Cambiar `cmd_dataset_build` para devolver (path, rows, tf, symbol)**

Modificar `cmd_dataset_build` para que:
- En lugar de devolver solo `List[str]`, devuelva una lista de dicts:

```python
[
  {"path": "...", "rows": 0, "symbol": "DOGEUSDT", "timeframe": "5m"},
  ...
]
```

Cada task debe devolver algo incluso si `rows == 0` (si el csv se escribió).

- [ ] **Step 2: Ajustar los puntos que escriben `datasets_manifest.json`**

Cambiar:

```python
_write_json(..., {"datasets": datasets, "backtests": backtests})
```

para que `datasets` sea esa lista de dicts (incluyendo rows=0).

- [ ] **Step 3: Smoke test rápido**

Run:

```bash
python scripts/tasks.py report:setup-edge --provider csv --workers 2
```

Expected:
- `datasets_manifest.json` contiene datasets con `rows: 0` si no hubo trades.

- [ ] **Step 4: Tests**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 3: checklist.md (mejoras + ayudas a debug)

**Files:**
- Modify/Create: `checklist.md`

- [ ] **Step 1: Escribir checklist con secciones mínimas**

Contenido recomendado:
- Pipeline: etapas y artefactos generados.
- Concurrencia: workers recomendados y límites por provider.
- Debug: flags CLI, logs esperados por etapa, qué mirar en `metrics` y en trades.
- Risk stops: interpretación y tuning.
- Sizing: `ai_risk` (1–5) + fallback 2% y cómo auditar `risk_pct_used`.
- SL/TP/BE/Trailing: estado actual y el diseño pendiente (BE+lock+trailing).
- Datasets: por timeframe, criterios de “rows=0”, y cómo interpretar.
- Tests: cómo correr y qué cubren.

- [ ] **Step 2: Validar que no rompe nada**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 4: Generar patch final consolidado contra origin/main

**Files:**
- Create: `nairatrading_hub_consolidated.patch`

- [ ] **Step 1: Generar patch**

Run:

```bash
git diff origin/main --no-color > /workspace/nairatrading_hub_consolidated.patch
wc -l /workspace/nairatrading_hub_consolidated.patch
```

Expected: Patch único listo para aplicar.

