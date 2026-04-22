# Setup Edge Report (multi-dataset + backtest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extender `scripts/analyze_runs.py` para calcular expectancy por setup (PnL y R), combinando múltiples datasets CSV y backtests JSON/JSONL, y producir outputs MD/JSON/CSV.

**Architecture:** Añadir loaders por fuente → normalizar trades → agregadores por setup/buckets → renderer Markdown/JSON/CSV. Mantener `analyze_runs.py` como CLI liviano, y extraer lógica a funciones puras para test.

**Tech Stack:** Python stdlib + pandas (ya en repo), pytest.

---

## Mapa de cambios (archivos)

**Modificar**
- `scripts/analyze_runs.py`

**Crear**
- `backend/tests/test_analyze_runs_setup_edge.py`

---

### Task 1: Tests RED (multi-dataset + backtest)

**Files:**
- Create: `backend/tests/test_analyze_runs_setup_edge.py`

- [ ] **Step 1: Test que espera tabla por setup y buckets**

Crear `backend/tests/test_analyze_runs_setup_edge.py`:

```python
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.analyze_runs import (
    load_dataset_csv,
    load_backtest_json,
    normalize_trade_rows,
    aggregate_by_setup,
)


def test_setup_edge_multi_sources():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ds1 = base / "a.csv"
        ds1.write_text("setup_primary,pnl,trend_age_bars,ema_compression\nbreakout,10,1,1.0\nbreakout,-5,2,1.2\n", encoding="utf-8")
        ds2 = base / "b.csv"
        ds2.write_text("setup_primary,pnl,trend_age_bars,ema_compression\npullback_ema,3,1,1.0\n", encoding="utf-8")
        bt = base / "bt.json"
        bt.write_text(json.dumps({"trades":[{"pnl":2.0,"setup_primary":"breakout","entry_meta":{"risk_r":1.0},"_features":{"trend_age_bars":1,"ema_compression":1.0}}]}), encoding="utf-8")

        rows = []
        rows += load_dataset_csv(str(ds1))
        rows += load_dataset_csv(str(ds2))
        rows += load_backtest_json(str(bt))
        norm = normalize_trade_rows(rows)
        agg = aggregate_by_setup(norm)
        assert "breakout" in agg
        assert agg["breakout"]["n_trades"] == 3
```

- [ ] **Step 2: Run test y verificar FAIL**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_analyze_runs_setup_edge.py`  
Expected: FAIL (funciones no existen todavía).

---

### Task 2: GREEN (loaders + normalización + agregación)

**Files:**
- Modify: `scripts/analyze_runs.py`
- Test: `backend/tests/test_analyze_runs_setup_edge.py`

- [ ] **Step 1: Añadir loaders**

Implementar en `scripts/analyze_runs.py`:
- `load_dataset_csv(path) -> list[dict]`
- `load_backtest_json(path) -> list[dict]` (devuelve trades list)

- [ ] **Step 2: Normalizar**

Implementar:
- `normalize_trade_rows(rows) -> list[dict]`
  - garantizar `setup_primary`, `pnl`, `risk_r`, `R`, `trend_age_bars`, `ema_compression`

- [ ] **Step 3: Agregar**

Implementar:
- `aggregate_by_setup(rows) -> dict`
  - n, winrate, avg/median pnl, avg/median R

- [ ] **Step 4: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_analyze_runs_setup_edge.py`  
Expected: PASS.

---

### Task 3: Buckets + renderers + CLI flags multi

**Files:**
- Modify: `scripts/analyze_runs.py`

- [ ] **Step 1: Buckets**

Implementar:
- `bucket_trend_age(x)`
- `bucket_ema_comp(x)`
- agregaciones por bucket (setup x bucket)

- [ ] **Step 2: Outputs**

Agregar:
- `--dataset-csv` (append)
- `--dataset-dir` (scan *.csv)
- `--backtest-json` (append)
- `--backtest-jsonl` (append)
- `--out-csv`

Y extender `build_markdown_report` para incluir tablas.

- [ ] **Step 3: Run full suite**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

