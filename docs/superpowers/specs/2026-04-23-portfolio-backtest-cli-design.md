# Spec: Cierre Checklist — Portfolio Backtest (metrics consistentes + CLI)

## Objetivo

Cerrar el ítem pendiente del checklist:

- “Portfolio-level backtest: equity/balance global por barra + drawdown consistente”

Haciendo dos mejoras en un último patch:

1) Alinear métricas de `portfolio_backtest` con `equity_curve` (cash + floating), para que `equity_last/total_pnl/CAGR` no queden inconsistentes cuando hay posiciones abiertas al final.
2) Exponer un subcomando en `scripts/tasks.py` para ejecutar el portfolio backtest y guardar artefactos en el run folder, igual que el resto del pipeline.

## Estado actual (resumen)

- Ya existe `NairaEngine.portfolio_backtest(...)`, calcula `equity_curve` y `max_drawdown_pct` sobre equity (cash+floating).
- Sin embargo, `metrics.equity_last` y `metrics.total_pnl` se calculan con `cash` (sin floating) al final del loop.
- No existe un comando en `scripts/tasks.py` para correr `portfolio_backtest` y persistir un artefacto.

## Cambios propuestos

### 1) Engine: métricas consistentes en portfolio_backtest

**Archivo:** `backend/app/engine/naira_engine.py`

Actualizar el bloque de métricas en `portfolio_backtest` para que:

- `equity_last = equity_curve[-1]` (equity mark-to-market, ya calculado por barra).
- `total_pnl = equity_last - starting_cash`
- `CAGR_pct` use `equity_last` (no `cash`) para coherencia con equity/drawdown.
- `open_positions_end` se mantiene.

**Criterio de aceptación:**

- `metrics.equity_last == equity_curve[-1]` (cuando hay datos).
- `metrics.total_pnl == metrics.equity_last - starting_cash`.
- `metrics.max_drawdown_pct >= 0` (ya existente).

### 2) CLI: subcomando backtest:portfolio

**Archivo:** `scripts/tasks.py`

Agregar subcomando `backtest:portfolio` al CLI de `scripts/tasks.py`.

**Flujo del comando:**

1) `data:update` (usa los flags de throttling/backoff existentes).
2) `scan` en TF `1h` (default) para obtener ranking por `opportunity_score`.
3) Seleccionar `top_syms` = `PIPELINE_TOPN` (o el default actual del runner).
4) Ejecutar `engine.portfolio_backtest(symbols=top_syms, provider=<provider>, base_timeframe="1h", ...)`.
5) Escribir un artefacto en el run folder:
   - `portfolio_backtest_1h.json`

**Flags del subcomando:**

- `--portfolio-base-timeframe` (default `1h`)
- `--portfolio-starting-cash` (default `10000.0`)
- `--portfolio-max-positions` (default `3`)

**Criterio de aceptación:**

- El comando crea el JSON en `backend/data/reports/YYYY-MM-DD/run_HHMMSS_<provider>/`.
- El JSON incluye `equity_curve`, `times` y `metrics.max_drawdown_pct`.

### 3) Tests

**Archivos:**

- `backend/tests/test_portfolio_backtest.py` (extender)
- `backend/tests/test_tasks_cli.py` (extender)

**Casos mínimos:**

1) `test_portfolio_metrics_equity_last_matches_equity_curve`:
   - `metrics.equity_last == equity_curve[-1]`
   - `metrics.total_pnl == metrics.equity_last - starting_cash`
2) `test_tasks_parser_has_backtest_portfolio`:
   - El parser acepta `backtest:portfolio` y flags básicos.

## Compatibilidad y riesgos

- No cambia la lógica de ejecución del portfolio; sólo alinea la forma de reportar métricas finales.
- Se añade un subcomando nuevo; no rompe los comandos existentes.

## Cómo verificar (local)

1) `pytest -q`
2) `python scripts/tasks.py backtest:portfolio --provider csv`

