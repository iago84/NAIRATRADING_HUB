# Diseño: Setup Classifier (multi-label) v1

## Objetivo

Añadir un clasificador de setups (más fino que `entry_kind`) que produzca **multi-label** con scores y razones, para:

- Analizar distribución de setups y edge real (expectancy por setup).
- Mejorar ranking en scan (sin mezclar fases).
- Guardar labels en trades y datasets para posterior auto-ML.

## Output

En `analyze` y `multi_brain`:

- `setup_primary`: string
- `setup_candidates`: lista ordenada desc (top-N configurable, default 3)
  - `type`: string
  - `score`: float 0..1
  - `reasons`: list[str] (máx 4)
  - `features`: dict[str,float] (subset estable para ML)

En backtest trades:
- `setup_primary`
- `setup_candidates_top3` (opcional, guardado en `_features` o `entry_meta`)

## Taxonomía (v1)

1) `breakout`
2) `break_retest`
3) `pullback_ema`
4) `pullback_level`
5) `mean_reversion`
6) `exhaustion`

## Features disponibles + 2 nuevas “baratas”

Reusar:
- `trend_age_bars`, `ema_compression`
- `alignment`, `slope_score`, `regression_r2`, `adx`
- `dist_ema25_atr`, `dist_ema80_atr` (ya existen en FEATURES)
- `level_confluence_score`, `nearest_support_distance_atr`, `nearest_resistance_distance_atr` (cuando estén disponibles en debug/features)
- `curvature`, `slope_z`

Agregar 2 nuevas (baratas, sin dependencias):

1) `wick_reject_ratio` (última vela):
   - `wick_reject_ratio = max(upper_wick, lower_wick) / max(1e-9, body)`
   - Se usa para MR y exhaustion.

2) `fractal_distance_atr` (distancia a fractal más cercano):
   - usar `latest_fractal_levels(df, lookback=2)` y ATR actual
   - `fractal_distance_atr = min(|price-fractal_high|, |price-fractal_low|) / ATR`

## Scoring (heurístico, explicable)

Cada setup devuelve score 0..1, con razones cortas. Luego se ordenan.

### breakout
Señales:
- `adx` alto, `alignment` alto, `regression_r2` alto, `ema_compression` baja
Penaliza:
- `trend_age_bars` alto

### break_retest
Señales:
- `entry_rules.break_retest_entry(...).ok` -> score alto
- si no, score medio si precio está cerca del fractal roto (via `fractal_distance_atr`)

### pullback_ema
Señales:
- `entry_rules.pullback_entry(...).ok` -> score alto
- refuerzo si `dist_ema25_atr` o `dist_ema80_atr` pequeño

### pullback_level
Señales:
- cerca de soporte/resistencia (si tenemos distancias) + `level_confluence_score` alto

### mean_reversion
Señales:
- `entry_rules.mean_reversion_entry(...).ok` y `wick_reject_ratio` alto
Penaliza:
- `adx` alto o compresión muy baja (tendencia fuerte)

### exhaustion
Señales:
- `trend_age_bars` alto + `ema_compression` alto + `wick_reject_ratio` alto + `curvature` contraria

## Integración

Nuevo módulo:
- `backend/app/engine/setup_classifier.py`

Puntos de integración:
- `NairaEngine.analyze(..., include_debug)` añade `setup_primary/setup_candidates` al output.
- `multi_brain.run_multi_brain(...)` añade lo mismo (y lo usa opcionalmente para ranking futuro).
- `backtest` guarda `setup_primary` en cada trade (y opcional top3).
- `dataset.build_trade_dataset` opcionalmente incluye `setup_primary` y scores top para ML.

## Testing

- Unit tests deterministas con un dataframe sintético:
  - vela con wick grande -> sube MR/exhaustion
  - fractal cercano -> sube break_retest
  - dist ema pequeña -> sube pullback_ema
- Smoke test con símbolo TEST del repo (no asserts rígidos de valores, sí de estructura y tipos).

