# One‑Click Pipeline (multi‑TF) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir `scripts/run_pipeline.py` sin argumentos + wrappers `.ps1/.sh` que actualicen datos, ejecuten scan/backtest/dataset en varios TF (mínimo 5m), y generen reporte de edge por setup (multi-source).

**Architecture:** Orquestador Python que usa funciones existentes (`HistoryStore`, `NairaEngine`, `run_multi_brain`, `build_trade_dataset`, `analyze_runs.py`) y escribe artefactos a `backend/data/reports/<date>/run_<time>/`.

**Tech Stack:** Python (stdlib + pandas), código existente del repo.

---

## Mapa de cambios (archivos)

**Crear**
- `scripts/run_pipeline.py`
- `scripts/run_pipeline.ps1`
- `scripts/run_pipeline.sh`
- `backend/tests/test_run_pipeline_smoke.py` (tests de piezas puras; sin depender de red)

**Modificar**
- `scripts/analyze_runs.py` (versión “setup edge report” multi-source)
- `backend/tests/test_analyze_runs_setup_edge.py`

---

### Task 1: Tests RED para analyze_runs v2 (multi datasets + backtests)

**Files:**
- Create: `backend/tests/test_analyze_runs_setup_edge.py`
- Modify: `scripts/analyze_runs.py`

- [ ] **Step 1: Añadir el test RED**

Crear `backend/tests/test_analyze_runs_setup_edge.py` con el contenido del plan anterior (multi-source + aggregate_by_setup).

- [ ] **Step 2: Ejecutar y verificar FAIL**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_analyze_runs_setup_edge.py`  
Expected: FAIL por funciones inexistentes.

---

### Task 2: GREEN para analyze_runs v2 (loaders + normalización + agregación + CLI flags)

**Files:**
- Modify: `scripts/analyze_runs.py`
- Test: `backend/tests/test_analyze_runs_setup_edge.py`

- [ ] **Step 1: Implementar loaders**

Agregar a `scripts/analyze_runs.py`:

```python
def load_dataset_csv(path: str) -> list[dict]: ...
def load_dataset_dir(dir_path: str) -> list[dict]: ...
def load_backtest_json(path: str) -> list[dict]: ...
def load_backtest_jsonl(path: str) -> list[dict]: ...
```

- [ ] **Step 2: Normalización + agregación**

Agregar:

```python
def normalize_trade_rows(rows: list[dict]) -> list[dict]: ...
def aggregate_by_setup(rows: list[dict]) -> dict: ...
def bucket_trend_age(x: int|None) -> str: ...
def bucket_ema_comp(x: float|None) -> str: ...
```

- [ ] **Step 3: Render Markdown/JSON/CSV**

Extender `build_markdown_report(...)` para incluir:
- tabla por setup con avg/median pnl y avg/median R
- matrices setup×bucket

- [ ] **Step 4: Ejecutar tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_analyze_runs_setup_edge.py`  
Expected: PASS.

---

### Task 3: Tests RED para run_pipeline (piezas puras y selección topN)

**Files:**
- Create: `backend/tests/test_run_pipeline_smoke.py`

- [ ] **Step 1: Test para selección topN**

```python
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.run_pipeline import pick_top_symbols

def test_pick_top_symbols_top10():
    items = [{"symbol": f"S{i}", "opportunity_score": float(i)} for i in range(30)]
    out = pick_top_symbols(items, top_n=10)
    assert len(out) == 10
    assert out[0] == "S29"
```

- [ ] **Step 2: Ejecutar y verificar FAIL**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_run_pipeline_smoke.py`  
Expected: FAIL (script no existe).

---

### Task 4: GREEN run_pipeline.py (sin args) + wrappers

**Files:**
- Create: `scripts/run_pipeline.py`
- Create: `scripts/run_pipeline.ps1`
- Create: `scripts/run_pipeline.sh`
- Test: `backend/tests/test_run_pipeline_smoke.py`

- [ ] **Step 1: Crear run_pipeline.py**

Requisitos:
- sin args
- env vars:
  - `PIPELINE_UNIVERSE` (30/100)
- TFs: `5m,15m,1h,4h,1d`
- TOP_N=10
- provider mixto:
  - usa `HistoryStore` y `BinanceRestOHLCVProvider` para llenar `history/binance`
  - export a `history/csv`
- scan por TF llamando a funciones directamente (no shell) o invocando `scripts/naira_pipeline.py scan` via `subprocess` (preferir imports para portabilidad).
- backtest: usar `NairaEngine.backtest(... provider='csv' ...)` con el csv canonical.
- dataset: usar `build_trade_dataset(...)`.
- reporte: llamar a `scripts/analyze_runs.py` via import de funciones o `subprocess`.

- [ ] **Step 2: Wrappers**

`scripts/run_pipeline.ps1`:
```powershell
$ErrorActionPreference = "Stop"
python scripts/run_pipeline.py
```

`scripts/run_pipeline.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
python3 scripts/run_pipeline.py
```

- [ ] **Step 3: Ejecutar tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q tests/test_run_pipeline_smoke.py`  
Expected: PASS.

---

### Task 5: Verificación final

- [ ] Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`
- [ ] Run (manual): `PYENV_VERSION=3.12.13 python scripts/run_pipeline.py`

