# Pipeline CLI + Auto-ML Loop + Docs (HTML/PDF-like) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un CLI único cross-platform (`argparse`) para descargar datos, correr pipelines (scan/backtest/dataset/train/calibrate/report) incorporando `TIMING_MODE=expansion` y generar documentación HTML/PDF-like.

**Architecture:** Un script `scripts/naira_pipeline.py` con subcomandos; wrappers sobre scripts/endpoints existentes; writer de manifests y docs generadas auto-contenidas.

**Tech Stack:** Python (argparse, hashlib, json), stack actual del repo (FastAPI engine + scripts existentes).

---

## Mapa de cambios (archivos)

**Crear**
- `scripts/naira_pipeline.py`
- `scripts/pipeline_lib/manifest.py`
- `scripts/pipeline_lib/paths.py`
- `scripts/pipeline_lib/docs_gen.py`
- `backend/tests/test_pipeline_cli.py`
- `docs/generated/.gitkeep`

**Modificar**
- `README.md`

---

### Task 1: Librería de paths + manifest

**Files:**
- Create: `scripts/pipeline_lib/paths.py`
- Create: `scripts/pipeline_lib/manifest.py`
- Test: `backend/tests/test_pipeline_cli.py`

- [ ] **Step 1: Implementar paths**

Crear `scripts/pipeline_lib/paths.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelinePaths:
    repo_root: str
    data_dir: str

    @property
    def history_dir(self) -> str:
        return os.path.join(self.data_dir, "history")

    @property
    def reports_dir(self) -> str:
        return os.path.join(self.data_dir, "reports")

    @property
    def docs_generated_dir(self) -> str:
        return os.path.join(self.repo_root, "docs", "generated")
```

- [ ] **Step 2: Implementar manifest writer**

Crear `scripts/pipeline_lib/manifest.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(path: str) -> Dict[str, Any]:
    st = os.stat(path)
    return {"path": path, "size": int(st.st_size), "sha256": sha256_file(path)}


@dataclass
class Manifest:
    job_id: str
    command: str
    args: Dict[str, Any]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    created_at: str
    git_head: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "command": self.command,
            "args": self.args,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "git_head": self.git_head,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_manifest(path: str, manifest: Manifest) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
```

- [ ] **Step 3: Test mínimo (sha256 + write)**

En `backend/tests/test_pipeline_cli.py` agregar:

```python
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.pipeline_lib.manifest import sha256_file, write_manifest, Manifest, now_iso


def test_manifest_write_and_hash():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text("hello", encoding="utf-8")
        h = sha256_file(str(p))
        assert len(h) == 64
        m = Manifest(job_id="x", command="test", args={}, inputs=[], outputs=[], created_at=now_iso())
        out = Path(td) / "manifest.json"
        write_manifest(str(out), m)
        assert out.exists()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 2: Docs generator (HTML + printable HTML)

**Files:**
- Create: `scripts/pipeline_lib/docs_gen.py`
- Create: `docs/generated/.gitkeep`
- Modify: `README.md`

- [ ] **Step 1: docs_gen**

Crear `scripts/pipeline_lib/docs_gen.py`:

```python
from __future__ import annotations

import os
from typing import Dict, List


def render_html(title: str, sections: List[Dict[str, str]]) -> str:
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'/>",
        f"<title>{title}</title>",
        "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:980px;margin:40px auto;line-height:1.5}code,pre{background:#f6f6f6;padding:2px 4px;border-radius:4px}pre{padding:12px;overflow:auto}@media print{a{color:black;text-decoration:none}}</style>",
        "</head><body>",
        f"<h1>{title}</h1>",
    ]
    for s in sections:
        parts.append(f"<h2>{s['h']}</h2>")
        parts.append(s["p"])
    parts.append("</body></html>")
    return "\n".join(parts)


def write_html(path: str, html: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
```

- [ ] **Step 2: `.gitkeep`**

Crear `docs/generated/.gitkeep` vacío.

- [ ] **Step 3: README**

Añadir sección “Pipeline CLI” con ejemplos de comandos.

---

### Task 3: CLI `scripts/naira_pipeline.py` (argparse)

**Files:**
- Create: `scripts/naira_pipeline.py`
- Test: `backend/tests/test_pipeline_cli.py`

- [ ] **Step 1: CLI skeleton**

Crear `scripts/naira_pipeline.py` con:
- `argparse` + subparsers
- `--data-dir` opcional (default: `backend/data`)
- `download` llama a `scripts/download_history.py`/`scripts/bulk_download.py` vía import (no shell)
- `--timing-mode` opcional (default: expansion) para comandos `scan/backtest/report`
- `docs` genera HTML en `docs/generated/pipeline.html` y `docs/generated/pipeline.pdf.html`
- `env` imprime rutas

Código inicial:

```python
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.pipeline_lib.paths import PipelinePaths
from scripts.pipeline_lib.docs_gen import render_html, write_html


def cmd_env(args: argparse.Namespace) -> int:
    pp = PipelinePaths(repo_root=REPO_ROOT, data_dir=args.data_dir)
    print(pp.data_dir)
    print(pp.history_dir)
    print(pp.reports_dir)
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    pp = PipelinePaths(repo_root=REPO_ROOT, data_dir=args.data_dir)
    sections = [
        {"h": "Comandos", "p": "<pre>python scripts/naira_pipeline.py env</pre>"},
    ]
    html = render_html("NAIRA Pipeline", sections)
    write_html(os.path.join(pp.docs_generated_dir, "pipeline.html"), html)
    write_html(os.path.join(pp.docs_generated_dir, "pipeline.pdf.html"), html)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="naira_pipeline")
    p.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "backend", "data"))
    sp = p.add_subparsers(dest="cmd", required=True)
    sp_env = sp.add_parser("env")
    sp_env.set_defaults(fn=cmd_env)
    sp_docs = sp.add_parser("docs")
    sp_docs.set_defaults(fn=cmd_docs)
    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Test parser**

En `backend/tests/test_pipeline_cli.py`:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.naira_pipeline import build_parser


def test_parser_env():
    p = build_parser()
    ns = p.parse_args(["env"])
    assert ns.cmd == "env"
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

### Task 4: Expandir subcomandos (download/scan/backtest/dataset/train/calibrate/report)

**Files:**
- Modify: `scripts/naira_pipeline.py`

- [ ] **Step 1: download**

Parámetros:
- `--provider`
- `--symbols` csv o `--watchlist <file>`
- `--timeframes` csv
- `--years`, `--limit`

Implementación: importar y llamar a funciones existentes (si los scripts actuales son solo CLI, factorizar funciones mínimas dentro del mismo archivo).

- [ ] **Step 2: scan/backtest wrappers**

Implementación vía imports del engine (sin HTTP) para modo local.

- [ ] **Step 3: dataset/train/calibrate**

Si hay endpoints TRADER, permitir `--api-url` + `--api-key` para llamar HTTP; si no, fallback a ejecución local (si existe función).

- [ ] **Step 4: report + manifest**

Guardar:
- `backend/data/reports/<date>/<job_id>/summary.json`
- `manifest.json`

- [ ] **Step 5: Run tests**

Run: `cd backend && PYENV_VERSION=3.12.13 python -m pytest -q`  
Expected: PASS.

---

## Auto-revisión del plan

- Sin dependencias externas (argparse).
- Soporta Windows/Linux con comandos de una línea.
- Artefactos y manifests reproducibles.
- Docs generadas en repo.
