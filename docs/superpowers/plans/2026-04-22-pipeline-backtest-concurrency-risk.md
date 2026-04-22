# Pipeline Backtests/Concurrencia/Riesgo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que el pipeline de `scripts/tasks.py all --provider binance` genere trades de forma consistente (especialmente en 5m) y ejecute más rápido con concurrencia, añadiendo límites de riesgo globales configurables en backtest.

**Architecture:** El pipeline expone flags CLI para `entry_mode`, concurrencia y risk-stops. El motor (`NairaEngine.backtest`) deja de forzar `entry_mode="regime"` en modo multi y aplica risk-stops en un helper puro testeable. El pipeline paraleliza scan/backtest/dataset por `(tf,symbol)` usando `ThreadPoolExecutor` evitando estado compartido no thread-safe.

**Tech Stack:** Python 3.10+, FastAPI (ya existente), pandas/numpy, `concurrent.futures` para concurrencia, pytest para tests.

---

## Cambios de Archivos (mapa)

**Modificar:**
- `scripts/tasks.py`
- `backend/app/engine/naira_engine.py`
- `backend/tests/test_tasks_cli.py`

**Crear:**
- `backend/app/engine/risk_stops.py`
- `backend/tests/test_risk_stops.py`

---

### Task 1: Añadir helper de risk-stops (testeable)

**Files:**
- Create: `backend/app/engine/risk_stops.py`
- Test: `backend/tests/test_risk_stops.py`

- [ ] **Step 1: Escribir test (falla) para `apply_risk_stop`**

```python
# backend/tests/test_risk_stops.py
from app.engine.risk_stops import RiskStopConfig, apply_risk_stop


def test_stop_immediate_on_max_drawdown():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_immediate",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=49.0, equity=49.0, has_open_position=False)
    assert res.triggered is True
    assert res.reason == "max_drawdown"
    assert res.should_terminate is True


def test_stop_after_close_waits_if_open_position():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_after_close",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=49.0, equity=49.0, has_open_position=True)
    assert res.triggered is True
    assert res.reason == "max_drawdown"
    assert res.should_terminate is False
    assert res.block_new_trades is True


def test_no_stop_when_healthy():
    cfg = RiskStopConfig(
        max_equity_drawdown_pct=50.0,
        free_cash_min_pct=0.20,
        policy="stop_immediate",
    )
    res = apply_risk_stop(cfg=cfg, starting_cash=100.0, cash=100.0, equity=100.0, has_open_position=False)
    assert res.triggered is False
```

- [ ] **Step 2: Ejecutar tests y verificar FAIL**

Run:

```bash
pytest -q backend/tests/test_risk_stops.py
```

Expected: FAIL por `ModuleNotFoundError` o `ImportError` (archivo/módulo no existe).

- [ ] **Step 3: Implementar `risk_stops.py`**

```python
# backend/app/engine/risk_stops.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


RiskStopPolicy = Literal["stop_immediate", "stop_no_new_trades", "stop_after_close"]


@dataclass(frozen=True)
class RiskStopConfig:
    max_equity_drawdown_pct: float = 50.0
    free_cash_min_pct: float = 0.20
    policy: RiskStopPolicy = "stop_immediate"


@dataclass(frozen=True)
class RiskStopResult:
    triggered: bool
    reason: str
    policy: str
    block_new_trades: bool
    should_terminate: bool
    threshold_equity: Optional[float]
    threshold_free_cash: Optional[float]


def apply_risk_stop(*, cfg: RiskStopConfig, starting_cash: float, cash: float, equity: float, has_open_position: bool) -> RiskStopResult:
    start = float(starting_cash)
    eq = float(equity)
    free_cash = float(cash)
    max_dd = float(cfg.max_equity_drawdown_pct)
    free_min = float(cfg.free_cash_min_pct)
    policy = str(cfg.policy)

    threshold_equity = start * (1.0 - max_dd / 100.0)
    threshold_free_cash = start * free_min

    reason = ""
    triggered = False
    if max_dd > 0 and eq <= threshold_equity:
        triggered = True
        reason = "max_drawdown"
    elif free_min > 0 and free_cash < threshold_free_cash:
        triggered = True
        reason = "free_cash_min"

    if not triggered:
        return RiskStopResult(
            triggered=False,
            reason="",
            policy=policy,
            block_new_trades=False,
            should_terminate=False,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_immediate":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=True,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_no_new_trades":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=False,
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    if policy == "stop_after_close":
        return RiskStopResult(
            triggered=True,
            reason=reason,
            policy=policy,
            block_new_trades=True,
            should_terminate=(not bool(has_open_position)),
            threshold_equity=float(threshold_equity),
            threshold_free_cash=float(threshold_free_cash),
        )

    return RiskStopResult(
        triggered=True,
        reason=reason,
        policy=policy,
        block_new_trades=True,
        should_terminate=True,
        threshold_equity=float(threshold_equity),
        threshold_free_cash=float(threshold_free_cash),
    )
```

- [ ] **Step 4: Ejecutar tests y verificar PASS**

Run:

```bash
pytest -q backend/tests/test_risk_stops.py
```

Expected: PASS.

- [ ] **Step 5: Commit (opcional si el usuario lo pide)**

```bash
git add backend/app/engine/risk_stops.py backend/tests/test_risk_stops.py
git commit -m "feat: add risk stop helper"
```

---

### Task 2: Hacer que backtest respete `entry_mode` (default `hybrid`) y aplique risk-stops

**Files:**
- Modify: `backend/app/engine/naira_engine.py`
- Test: `backend/tests/test_risk_stops.py` (ya cubre la lógica base)

- [ ] **Step 1: Ajustar selección de entry_mode**

Cambiar el bloque:

```python
entry_mode = str(self.config.entry_mode or "hybrid")
if str(self.config.strategy_mode or "single").lower() == "multi":
    entry_mode = "regime"
```

por:

```python
entry_mode = str(self.config.entry_mode or "hybrid")
```

en:
- `NairaEngine.backtest(...)`
- `NairaEngine.portfolio_backtest(...)`

- [ ] **Step 2: Cablear risk-stops en `backtest(...)`**

1) Importar:

```python
from .risk_stops import RiskStopConfig, apply_risk_stop
```

2) Ampliar la firma de `backtest` con parámetros nuevos (defaults):

```python
max_equity_drawdown_pct: float = 50.0,
free_cash_min_pct: float = 0.20,
risk_stop_policy: str = "stop_immediate",
```

3) Inicializar estado de risk-stop antes del loop:

```python
risk_cfg = RiskStopConfig(
    max_equity_drawdown_pct=float(max_equity_drawdown_pct),
    free_cash_min_pct=float(free_cash_min_pct),
    policy=str(risk_stop_policy),  # type: ignore[arg-type]
)
risk_triggered = False
risk_reason = ""
risk_policy = str(risk_stop_policy)
risk_stop_at_index = None
risk_stop_at_time = None
block_new_trades = False
```

4) En cada iteración del loop principal (antes de abrir posición) evaluar:

```python
floating = 0.0
if side is not None and entry is not None:
    sign = 1.0 if side == "buy" else -1.0
    floating = (price - float(entry)) * sign * float(qty)
equity_now = float(cash + floating)
rs = apply_risk_stop(cfg=risk_cfg, starting_cash=float(starting_cash), cash=float(cash), equity=float(equity_now), has_open_position=bool(side is not None))
if rs.triggered:
    risk_triggered = True
    risk_reason = str(rs.reason)
    risk_policy = str(rs.policy)
    block_new_trades = bool(rs.block_new_trades)
    if risk_stop_at_index is None:
        risk_stop_at_index = int(i)
        risk_stop_at_time = pd.to_datetime(dt_arr[i]).isoformat()
    if rs.should_terminate:
        break
```

5) Condicionar la lógica de entrada:
- si `block_new_trades` es `True`, saltar el bloque de apertura (pero permitir lógica de gestión/cierre si hay posición).

- [ ] **Step 3: Añadir métricas de risk-stop al output**

Dentro de `metrics = {...}` agregar:

```python
"risk_stop_triggered": bool(risk_triggered),
"risk_stop_reason": str(risk_reason),
"risk_stop_policy": str(risk_policy),
"risk_stop_at_index": int(risk_stop_at_index) if risk_stop_at_index is not None else None,
"risk_stop_at_time": str(risk_stop_at_time) if risk_stop_at_time is not None else "",
"risk_threshold_equity": float(float(starting_cash) * (1.0 - float(max_equity_drawdown_pct) / 100.0)),
"risk_threshold_free_cash": float(float(starting_cash) * float(free_cash_min_pct)),
```

- [ ] **Step 4: Ejecutar suite mínima**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit (opcional si el usuario lo pide)**

```bash
git add backend/app/engine/naira_engine.py
git commit -m "feat: honor entry_mode and add risk stops to backtest"
```

---

### Task 3: Extender CLI de `scripts/tasks.py` (entry_mode + workers + risk-stops)

**Files:**
- Modify: `scripts/tasks.py`
- Modify: `backend/tests/test_tasks_cli.py`

- [ ] **Step 1: Ampliar parser con flags nuevos**

En `build_parser()` agregar argumentos:

```python
sub.add_argument("--entry-mode", default=os.getenv("PIPELINE_ENTRY_MODE", "hybrid"))
sub.add_argument("--workers", type=int, default=int(os.getenv("PIPELINE_WORKERS", "8")))
sub.add_argument("--update-workers", type=int, default=int(os.getenv("PIPELINE_UPDATE_WORKERS", "2")))
sub.add_argument("--max-equity-drawdown-pct", type=float, default=float(os.getenv("PIPELINE_MAX_DD_PCT", "50.0")))
sub.add_argument("--free-cash-min-pct", type=float, default=float(os.getenv("PIPELINE_FREE_CASH_MIN_PCT", "0.20")))
sub.add_argument("--risk-stop-policy", default=os.getenv("PIPELINE_RISK_STOP_POLICY", "stop_immediate"), choices=["stop_immediate", "stop_no_new_trades", "stop_after_close"])
```

- [ ] **Step 2: Actualizar tests del parser**

Modificar `backend/tests/test_tasks_cli.py`:

```python
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.tasks import build_parser


def test_tasks_parser_all_binance_defaults():
    p = build_parser()
    ns = p.parse_args(["all", "--provider", "binance"])
    assert ns.cmd == "all"
    assert ns.provider == "binance"
    assert ns.entry_mode == "hybrid"
    assert ns.risk_stop_policy == "stop_immediate"


def test_tasks_parser_all_binance_overrides():
    p = build_parser()
    ns = p.parse_args(
        [
            "all",
            "--provider",
            "binance",
            "--entry-mode",
            "pullback",
            "--workers",
            "16",
            "--update-workers",
            "3",
            "--max-equity-drawdown-pct",
            "40",
            "--free-cash-min-pct",
            "0.30",
            "--risk-stop-policy",
            "stop_after_close",
        ]
    )
    assert ns.entry_mode == "pullback"
    assert ns.workers == 16
    assert ns.update_workers == 3
    assert ns.max_equity_drawdown_pct == 40
    assert ns.free_cash_min_pct == 0.30
    assert ns.risk_stop_policy == "stop_after_close"
```

- [ ] **Step 3: Ejecutar tests**

Run:

```bash
pytest -q backend/tests/test_tasks_cli.py
```

Expected: PASS.

- [ ] **Step 4: Commit (opcional si el usuario lo pide)**

```bash
git add scripts/tasks.py backend/tests/test_tasks_cli.py
git commit -m "feat: extend tasks cli with entry mode, workers, and risk params"
```

---

### Task 4: Paralelizar scan/backtest/dataset en `scripts/tasks.py`

**Files:**
- Modify: `scripts/tasks.py`

- [ ] **Step 1: Añadir ejecución concurrente sin estado compartido**

1) Importar:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

2) Cambiar firmas para aceptar `workers` y `entry_mode` + risk params:
- `cmd_scan(..., workers: int, entry_mode: str)`
- `cmd_backtest_top(..., workers: int, entry_mode: str, max_equity_drawdown_pct: float, free_cash_min_pct: float, risk_stop_policy: str)`
- `cmd_dataset_build(..., workers: int, entry_mode: str)`
- `cmd_data_update(..., update_workers: int)` (concurrencia baja)

3) Evitar compartir `NairaEngine` entre threads:
- Instanciar un engine dentro de cada “job” o usar `threading.local()` para cache por thread.

Ejemplo patrón de job:

```python
def _scan_one(sym: str, tf: str) -> dict | None:
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
    r, _ = run_multi_brain(engine=eng, symbol=sym, provider=str(provider), base_timeframe=tf, tranche="T1", include_debug=False)
    return r
```

Luego:

```python
with ThreadPoolExecutor(max_workers=int(workers)) as ex:
    futs = [ex.submit(_scan_one, sym, tf) for sym in symbols for tf in tfs]
    for f in as_completed(futs):
        v = f.result()
        if v:
            rows.append(v)
```

- [ ] **Step 2: Backtest concurrente por símbolo**

Job:

```python
def _bt_one(sym: str, tf: str) -> tuple[str, dict] | None:
    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
    r = eng.backtest(
        symbol=sym,
        provider=str(provider),
        base_timeframe=tf,
        max_bars=5000,
        max_equity_drawdown_pct=float(max_equity_drawdown_pct),
        free_cash_min_pct=float(free_cash_min_pct),
        risk_stop_policy=str(risk_stop_policy),
    )
    return (tf, r)
```

Y escribir cada resultado a su json correspondiente.

- [ ] **Step 3: Dataset build concurrente por símbolo**

Patrón análogo al backtest; cada job llama `build_trade_dataset(...)` con engine con `entry_mode` configurado.

- [ ] **Step 4: Integración en `main()`**

En `main(argv)` capturar args:

```python
entry_mode = str(args.entry_mode)
workers = int(args.workers)
update_workers = int(args.update_workers)
max_equity_drawdown_pct = float(args.max_equity_drawdown_pct)
free_cash_min_pct = float(args.free_cash_min_pct)
risk_stop_policy = str(args.risk_stop_policy)
```

y propagar a cada cmd.

- [ ] **Step 5: Smoke test del pipeline (local)**

Run:

```bash
python scripts/tasks.py all --provider binance --entry-mode hybrid --workers 8 --update-workers 2
```

Expected:
- Se crea un nuevo `backend/data/reports/<fecha>/run_*_binance/`.
- Dentro, una parte significativa de `backtest_5m_*.json` contiene `metrics.trades > 0` (si el mercado y el histórico lo permiten).

- [ ] **Step 6: Ejecutar tests**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 7: Commit (opcional si el usuario lo pide)**

```bash
git add scripts/tasks.py
git commit -m "feat: parallelize tasks pipeline"
```

---

## Self-Review (del plan)

- Cobertura del spec: entry_mode hybrid, risk stops globales, concurrencia, tests y compatibilidad de outputs.
- Sin placeholders: cada step incluye código/commands concretos.
- Nombres consistentes: flags CLI, campos de métricas y políticas.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-pipeline-backtest-concurrency-risk.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

