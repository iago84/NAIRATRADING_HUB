# Diseño: Reporte Edge por Setup (multi-dataset + backtest)

## Objetivo

Extender `scripts/analyze_runs.py` para medir edge real “por setup”, combinando múltiples fuentes:

- Datasets CSV (de `build_trade_dataset`) con `setup_primary`, `pnl`, features.
- Backtests JSON/JSONL (trades) con `pnl` y `setup_primary`.
- Scan JSON (opcional) para distribución de setups en señales.

El reporte debe producir:

- Expectancy **PnL** (USDT) y **R-multiple** (pnl / risk_r cuando exista).
- Breakdown por `setup_primary` y por buckets de timing (`trend_age_bars`, `ema_compression`).
- Outputs en Markdown + JSON + CSV.

## Inputs (multi-source)

CLI:

- `--dataset-csv <path>` (repetible)
- `--dataset-dir <dir>` (busca `*.csv` dentro; filtro opcional)
- `--backtest-json <path>` (repetible) → objeto con `trades` list
- `--backtest-jsonl <path>` (repetible) → cada línea tiene `trades` o `metrics`
- `--scan-json <path>` (repetible) → array de señales

Filtros:

- `--symbol <SYM>` (opcional)
- `--provider <provider>` (opcional)
- `--timeframe <tf>` (opcional)
- `--min-trades <n>` para incluir setup en tabla

## Normalización de campos

Unificar cada “trade row” a:

- `setup_primary` (string, default `unknown`)
- `pnl` (float)
- `risk_r` (float|None)
- `R` (float|None) = pnl / risk_r si risk_r>0
- `trend_age_bars` (int|None)
- `ema_compression` (float|None)
- `symbol/provider/base_timeframe` (opcional)

De dataset:
- `setup_primary`, `pnl`, `trend_age_bars`, `ema_compression` (si están)
- `risk_r`: no siempre está → `None`

De backtest:
- `setup_primary` viene en trade o en `entry_meta.setup_primary`
- `pnl` viene en trade
- `risk_r` viene de `trade.entry_meta.risk_r` o `trade._features.risk_r` si existe; si no, `None`

## Buckets

- `trend_age_bucket`:
  - `<=2`, `3-5`, `6-8`, `>8`
- `ema_comp_bucket`:
  - `<=1.5`, `1.5-2`, `2-5`, `>5`

## Métricas por setup

Para cada `setup_primary`:
- `n_trades`
- `win_rate_pct`
- `avg_pnl`, `median_pnl`
- `avg_R`, `median_R` (si R disponible)

Tablas extra:
- `setup_primary x trend_age_bucket` (n, avg_pnl, avg_R)
- `setup_primary x ema_comp_bucket` (n, avg_pnl, avg_R)

## Outputs

- `--out-md <path>`: reporte Markdown con tablas
- `--out-json <path>`: payload con rows agregadas + resumen
- `--out-csv <path>`: tabla por setup (1 row por setup)

## Testing

Tests unitarios con fixtures temporales:
- 2 dataset csv distintos (múltiples) → se combinan
- 1 backtest json con trades → se combina
- asserts sobre:
  - presencia de tabla por setup
  - cálculo de expectancy PnL correcto
  - cálculo de buckets correcto

