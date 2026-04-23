# Portfolio Backtest (metrics consistentes + CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el ítem pendiente de portfolio backtest haciendo métricas consistentes (equity_last/total_pnl/CAGR) y agregando un comando `backtest:portfolio` en `scripts/tasks.py` (default TF `1h`).

**Architecture:** Ajustar `NairaEngine.portfolio_backtest` para que las métricas finales se basen en `equity_curve` (cash+floating). Extender `scripts/tasks.py` con un subcomando que ejecute el flujo update→scan→portfolio_backtest y escriba un artefacto JSON en el run folder.

**Tech Stack:** Python, pytest.

---

## Cambios de archivos (mapa)

- Modify: `backend/app/engine/naira_engine.py` (métricas de `portfolio_backtest`)
- Modify: `scripts/tasks.py` (nuevo subcomando `backtest:portfolio`)
- Test: `backend/tests/test_portfolio_backtest.py` (métricas consistentes)
- Test: `backend/tests/test_tasks_cli.py` (parser del nuevo subcomando)
- Modify: `checklist.md` (marcar ítem portfolio-level como completado)

---

### Task 1: Test de métricas consistentes (portfolio_backtest)

**Files:**
- Modify: `backend/tests/test_portfolio_backtest.py`

- [ ] **Step 1: Añadir test que fuerce posiciones abiertas y valide equity_last**

Agregar al final del archivo:

```python
def test_portfolio_metrics_equity_last_matches_equity_curve():
    cfg = NairaConfig(strategy_mode="multi", entry_mode="hybrid")
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=cfg)
    r = eng.portfolio_backtest(
        symbols=["LTCUSDT", "BTCUSDT"],
        provider="csv",
        base_timeframe="1h",
        starting_cash=10000.0,
        max_positions=2,
        max_bars=400,
    )
    assert "error" not in r
    eq = r.get("equity_curve") or []
    assert eq
    m = r.get("metrics") or {}
    assert abs(float(m.get("equity_last")) - float(eq[-1])) < 1e-9
    assert abs(float(m.get("total_pnl")) - (float(m.get("equity_last")) - 10000.0)) < 1e-9
```

- [ ] **Step 2: Ejecutar el test y verificar FAIL**

Run:

```bash
pytest -q backend/tests/test_portfolio_backtest.py::test_portfolio_metrics_equity_last_matches_equity_curve
```

Expected: FAIL (equity_last/total_pnl aún calculados con `cash`).

---

### Task 2: Engine — métricas consistentes en portfolio_backtest

**Files:**
- Modify: `backend/app/engine/naira_engine.py`

- [ ] **Step 1: Cambiar métricas para usar equity_last=equity_curve[-1]**

En `portfolio_backtest`, después de calcular `eq = ...` y `max_dd_pct`, definir:

```python
equity_last = float(eq[-1]) if len(eq) else float(cash)
total_pnl = float(equity_last - float(starting_cash))
```

y cambiar:

- `metrics["equity_last"]` → `equity_last`
- `metrics["total_pnl"]` → `total_pnl`
- cálculo de `CAGR_pct` → usar `equity_last` en el ratio (en lugar de `cash`)

- [ ] **Step 2: Ejecutar el test y verificar PASS**

Run:

```bash
pytest -q backend/tests/test_portfolio_backtest.py::test_portfolio_metrics_equity_last_matches_equity_curve
```

Expected: PASS.

- [ ] **Step 3: Ejecutar suite completa**

Run:

```bash
pytest -q
```

Expected: PASS.

---

### Task 3: CLI — subcomando backtest:portfolio

**Files:**
- Modify: `scripts/tasks.py`
- Test: `backend/tests/test_tasks_cli.py`

- [ ] **Step 1: Agregar subcomando al parser**

1) Agregar `"backtest:portfolio"` al listado de comandos en `build_parser()`.
2) Agregar flags:

```python
sub.add_argument("--portfolio-base-timeframe", default=os.getenv("PIPELINE_PORTFOLIO_TF", "1h"))
sub.add_argument("--portfolio-starting-cash", type=float, default=float(os.getenv("PIPELINE_PORTFOLIO_CASH", "10000") or "10000"))
sub.add_argument("--portfolio-max-positions", type=int, default=int(os.getenv("PIPELINE_PORTFOLIO_MAX_POS", "3") or "3"))
```

- [ ] **Step 2: Implementar handler en main**

En `main()`, agregar branch:

- Ejecutar `cmd_data_update(...)`
- Ejecutar `cmd_scan(...)` sólo para TF `1h`
- Seleccionar `top_syms` con `pick_top_symbols(...)`
- Crear `NairaEngine` local y llamar `engine.portfolio_backtest(...)`
- Escribir `portfolio_backtest_1h.json` en `run_dir`

- [ ] **Step 3: Test del parser**

En `backend/tests/test_tasks_cli.py`, agregar:

```python
def test_parser_backtest_portfolio():
    p = build_parser()
    ns = p.parse_args(["backtest:portfolio", "--provider", "csv"])
    assert ns.cmd == "backtest:portfolio"
```

- [ ] **Step 4: Ejecutar tests relevantes**

Run:

```bash
pytest -q backend/tests/test_tasks_cli.py::test_parser_backtest_portfolio
pytest -q backend/tests/test_portfolio_backtest.py
```

Expected: PASS.

---

### Task 4: Checklist

**Files:**
- Modify: `checklist.md`

- [ ] **Step 1: Marcar el ítem portfolio-level como completado**

En la sección “Mejoras Prioritarias (próximas)”, marcar:

- [x] Portfolio-level backtest: equity/balance global por barra + drawdown consistente (sin signo negativo).

- [ ] **Step 2: Ejecutar suite**

Run:

```bash
pytest -q
```

Expected: PASS.

