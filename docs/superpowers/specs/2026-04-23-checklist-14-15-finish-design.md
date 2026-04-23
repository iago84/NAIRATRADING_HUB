# Checklist 14–15 Finish Design

**Goal:** Completar `checklist.md` secciones 14–15 con cambios verificables en pipeline, auditoría, métricas de PnL, gates, y mejoras de ejecución/backtest.

**Scope:** Dos entregas.

---

## Entrega 1 (Checklist 14): Operativa + Debug

### 1) Pipeline end-to-end + artefactos por run

**Objetivo**
- `python scripts/tasks.py all ...` debe generar consistentemente artefactos por run y enlazar análisis en HTML.

**Artefactos esperados (mínimo)**
- `scan_<tf>.json`
- `backtest_<tf>_<sym>.json` (y opcionalmente `backtest_<tf>_<sym>_lev{N}.json` si `--leverage-sweep`)
- `datasets_manifest.json`
- `setup_edge.md`
- `setup_edge.json`
- `setup_edge.html`
- `train.json` (si se ejecuta training en el pipeline)
- `calibration.json` (si se ejecuta calibración en el pipeline)

**Cambios**
- Validación fuerte en `scripts/tasks.py` tras cada etapa: si un artefacto clave no existe, el comando falla con exit code != 0.

### 2) Auditoría de sizing por trade (entry_meta)

**Objetivo**
- Registrar el sizing realmente usado por trade para depurar fallback/AI sizing.

**Campos nuevos**
- `entry_meta.risk_pct_used`: float (porcentaje de riesgo efectivo usado en el sizing del trade).
- `entry_meta.sizing_mode_used`: str con valores:
  - `ai_risk`
  - `fixed_risk`
  - `fixed_qty`
  - `fixed_risk_fallback` (cuando se pidió `ai_risk` pero se acabó usando fixed-risk por fallback).

**Persistencia**
- Incluir estos campos en el `entry_meta` que se escribe en cada trade dentro del JSON de backtest.

### 3) “TP negativo” / PnL raro: métricas por trade con parciales

**Objetivo**
- Eliminar confusión de PnL cuando hay parciales, sin romper compatibilidad.

**Decisión de compatibilidad (aprobada)**
- Mantener `trade.pnl` con el significado actual (PnL del remanente/cierre final).

**Campos nuevos**
- `trade.pnl_partials`: lista de floats (PnL materializado en parciales).
- `trade.pnl_total`: float = `trade.pnl + sum(trade.pnl_partials)`.

**Notas**
- No cambiar el mecanismo de cash; sólo registrar explícitamente parciales + total.
- Garantizar que `pnl_total` refleja lo que realmente incrementa el equity (cash + PnL final).

### 4) Timing gate bloqueando demasiado

**Objetivo**
- Hacer visible si el timing gate está bloqueando entradas y por qué.

**Cambios**
- Asegurar que `metrics.gates_timing_blocked` se reporta siempre.
- Incluir en `setup_edge.html` un bloque “Timing gate” con:
  - `gates_timing_blocked`
  - resumen corto de `late_entry_report.recommendations` (si existe)

---

## Entrega 2 (Checklist 15): Mejoras Prioritarias

### 1) Gestión de salida: BE + lock + trailing sin conflicto

**Objetivo**
- Añadir “lock” de beneficios basado en R/ATR y coordinar con trailing para evitar doble actualización conflictiva.

**Requisitos**
- BE mantiene comportamiento actual.
- Lock y trailing deben tener precedencia explícita y trazabilidad en `trade.exit_meta` (o estructura equivalente si ya existe).

### 2) Métricas por trade: explicabilidad de no-entrada

**Objetivo**
- Contadores por gate y/o regla para tuning rápido.

**Requisitos**
- Métricas agregadas por símbolo/TF y global, persistidas en `metrics` del backtest.

### 3) Provider throttling/backoff en data:update

**Objetivo**
- Proteger llamadas a provider (Binance) con throttling/backoff configurable.

**Requisitos**
- Flags en `scripts/tasks.py` (por ejemplo):
  - `--update-min-sleep-ms`
  - `--update-backoff-ms`
  - `--update-max-retries`
- Aplicación en el loop de OHLC paginado.

### 4) Portfolio-level backtest: equity/balance global por barra

**Objetivo**
- Validar y corregir drawdown y equity a nivel portfolio.

**Requisitos**
- Métricas consistentes (sin signos incorrectos) y test de regresión.

---

## Testing y verificación

### Verificación Entrega 1
- `python -m py_compile scripts/tasks.py backend/app/engine/naira_engine.py scripts/analyze_runs.py`
- Smoke de `scripts/analyze_runs.py` generando `setup_edge.html` con:
  - `--dataset-dir backend/data/datasets`
  - `--backtest-json <un backtest existente>`
- Ejecución `python scripts/tasks.py all --provider csv ...` (no destructiva) para validar artefactos.

### Verificación Entrega 2
- Unit tests específicos para:
  - `pnl_partials` + `pnl_total` (no negativos por inconsistencia cuando hay parciales).
  - lock/trailing precedence.
  - throttling/backoff (test con provider mock/fake).
  - portfolio backtest equity/drawdown.

---

## Acceptance Criteria

### Entrega 1
- Checklist 14 queda en `[x]` para: flags, datasets manifest, auditoría de sizing, pnl_partials/pnl_total, y reporte HTML.
- `tasks.py all` produce `setup_edge.html` y contiene secciones Datasets/Backtests y resumen de timing gate.

### Entrega 2
- Checklist 15 queda en `[x]` para los 5 ítems.
- Tests pasan.

