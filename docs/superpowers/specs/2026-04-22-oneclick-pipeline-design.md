# Diseño: One‑Click Pipeline (multi‑TF, mixto, sin argumentos)

## Objetivo

Crear un pipeline “one‑click” sin argumentos que ejecute el recorrido completo:

1) Mantener CSV local actualizado (provider mixto: binance → csv canonical)
2) Scan multi‑brain con `TIMING_MODE=expansion`
3) Backtest batch de top N símbolos por timeframe
4) Dataset build (trade dataset) para ML
5) Reporte de edge por setup combinando múltiples datasets/backtests
6) (Opcional) train/calibrate en loop si hay funciones disponibles

Debe funcionar en Windows y Linux.

## Artefactos

Por cada ejecución se crea un run folder:

- `backend/data/reports/YYYY-MM-DD/run_HHMMSS/`

Contenido mínimo:

- `scan_<tf>.json`
- `backtest_<tf>_<symbol>.json`
- `datasets_manifest.json` (lista de datasets generados)
- `setup_edge.md`
- `setup_edge.json`
- `setup_edge.csv`
- `pipeline.log` (texto)

## Universo y timeframes

### Timeframes (mínimo 5m)

Timeframes default:
- `["5m", "15m", "1h", "4h", "1d"]`

### Universo (default 30, opción 100)

Sin argumentos, pero con env var simple:

- Default: 30 símbolos
- Si `PIPELINE_UNIVERSE=100` → 100 símbolos

Fuente de símbolos:
- `backend/data/watchlists/crypto_top30.json` para 30
- `backend/data/watchlists/crypto_top100.json` para 100

## Provider mixto + CSV canonical

Reglas:

- Canonical local siempre: `backend/data/history/csv/<SYMBOL>/<TF>.csv`
- Si falta o está viejo:
  - descargar desde binance a `backend/data/history/binance/...` (si hay red)
  - normalizar/upsert y exportar a `history/csv/...`

Refresco por ventana (para no re‑descargar todo):
- 5m: últimos 7–14 días
- 15m: últimos 30 días
- 1h: últimos 180 días
- 4h: últimos 365 días
- 1d: últimos 3 años

## Scan + Backtest + Dataset

Por cada timeframe `tf`:

1) Scan:
- comando equivalente:
  - `python scripts/naira_pipeline.py --timing-mode expansion scan --provider csv --base-timeframe <tf> --symbols <list> --mode multi --balance-usdt 1000`
- guardar `scan_<tf>.json`

2) Selección:
- tomar top `TOP_N=10` por `opportunity_score`

3) Backtest:
- ejecutar backtest por símbolo top y guardar `backtest_<tf>_<sym>.json`
- el backtest debe producir `trades[].setup_primary` y `pnl`

4) Dataset ML:
- generar dataset por símbolo+tf (trade dataset) y guardarlo en `backend/data/datasets/`

## Reporte Edge por Setup (multi-source)

Ejecutar `scripts/analyze_runs.py` (versión extendida) combinando:
- todos los datasets generados por el run
- todos los backtests generados por el run

Métricas:
- expectancy PnL (USDT)
- expectancy R (cuando exista risk_r)
- breakdown por setup y buckets (`trend_age_bars`, `ema_compression`)

## Wrappers

- `scripts/run_pipeline.py` (core)
- `scripts/run_pipeline.ps1` → llama a python y deja logs
- `scripts/run_pipeline.sh` → idem

