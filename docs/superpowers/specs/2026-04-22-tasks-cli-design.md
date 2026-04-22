# Diseño: Scripts Tasks CLI (por provider)

## Objetivo

Añadir un runner de comandos `scripts/tasks.py` que ejecute el flujo completo por provider (uno por run):

- `binance` / `mt5` / `csv`

Debe permitir correr pasos individuales y un `all` que encadene todo.

## Principios

- Un run folder por ejecución:
  - `backend/data/reports/YYYY-MM-DD/run_HHMMSS_<provider>/`
- Artefactos siempre en el run folder:
  - `scan_<tf>.json`
  - `backtest_<tf>_<sym>.json`
  - `datasets_manifest.json`
  - `setup_edge.md/json`
  - `train.json` (resumen)
  - `calibration.json`
- Modelo AI global:
  - `backend/data/models/naira_logreg_stack.json`

## Defaults

- TFs: `5m, 15m, 1h, 4h, 1d`
- Universo: 30 símbolos por defecto (env `PIPELINE_UNIVERSE=100` para 100)
- Top backtests por TF: 10 (env `PIPELINE_TOPN` opcional)
- Timing: `expansion` (via `--timing-mode` al CLI scan)

## Comandos

- `data:update --provider <p>`
- `scan --provider <p>`
- `backtest:top --provider <p>`
- `backtest:global --provider <p>`
- `dataset:build --provider <p>`
- `report:setup-edge --provider <p>`
- `train:stack --provider <p>`
- `train:calibrate --provider <p>`
- `all --provider <p>`

## Training

`train:stack`:
- usa `backend/app/engine/model.train_logreg_sgd_multi`
- datasets input: todos los datasets del run (`datasets_manifest.json`)
- output: `backend/data/models/naira_logreg_stack.json`

`train:calibrate`:
- usa `backend/app/engine/calibration.calibration_report`
- dataset: dataset concatenado temporal (desde inputs)
- output: `calibration.json` en run folder

