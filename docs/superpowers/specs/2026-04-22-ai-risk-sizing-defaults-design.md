# Diseño: AI Risk Sizing como default (y fallback a 2% fixed risk)

## Contexto

En los backtests actuales es fácil observar PnL “microscópico” en activos baratos (p.ej. DOGE) porque muchas ejecuciones acaban usando `fixed_qty=1` (cantidad fija), lo que desconecta el tamaño de la posición del capital (`starting_cash`).

Además, para poder entrenar y evaluar sizing asistido por AI de forma consistente, el pipeline debe ejecutar por defecto con un modo de sizing que:

1. Escale el tamaño con el riesgo.
2. Use `ai_prob_entry` cuando exista modelo.
3. Mantenga un comportamiento razonable cuando no exista modelo (fallback).

## Objetivo

Hacer que el pipeline (`scripts/tasks.py`) y los backtests usen `sizing_mode="ai_risk"` como default, y que la falta de AI no reduzca el sizing a `fixed_qty=1`, sino que haga fallback a `fixed_risk` con un riesgo fijo razonable.

## Comportamiento acordado

### 1) Default: `ai_risk` primero

- `sizing_mode = "ai_risk"` por defecto en el pipeline.
- `ai_risk_min_pct = 1.0`
- `ai_risk_max_pct = 5.0`
- Cuando `ai_prob_entry` está disponible:
  - `risk_pct = ai_risk_min_pct + (ai_risk_max_pct - ai_risk_min_pct) * ai_prob_entry`
  - Se usa `risk_pct` para calcular `qty` en función de `R = abs(entry - sl)`:
    - `risk_cash = cash * (risk_pct / 100)`
    - `qty = min(risk_cash / R, qty_max)` (respetando `max_leverage`)

### 2) Fallback: fixed risk al 2%

Cuando `ai_prob_entry` sea `null` (modelo no cargado / no disponible), el modo `ai_risk` debe:

- Caer a `fixed_risk` con:
  - `risk_per_trade_pct = 2.0`
- No volver a `fixed_qty=1`.

Esto garantiza que:

- El sizing es “capital-aware”.
- Las métricas (CAGR, DD, PF) se vuelven comparables entre símbolos.
- El dataset generado refleje el efecto de riesgo real, aunque no haya modelo.

## Interfaz propuesta (pipeline)

En `scripts/tasks.py`:

- Parámetros configurables por CLI/env:
  - `--sizing-mode` (default: `ai_risk`)
  - `--risk-per-trade-pct` (default: `2.0`)  (usado en fallback y en fixed_risk)
  - `--ai-risk-min-pct` (default: `1.0`)
  - `--ai-risk-max-pct` (default: `5.0`)
  - `--max-leverage` (default: 1.0)

## Observabilidad recomendada (para entrenar)

En cada trade (o `entry_meta`) registrar:

- `ai_prob_entry` (ya existe)
- `risk_pct_used` (nuevo)
- `sizing_mode_used` (nuevo; `ai_risk` o `fixed_risk_fallback`)
- `filled_qty` (ya existe)

Esto permite auditar:

- qué % de riesgo se aplicó realmente
- cuándo hubo fallback por falta de AI

## Validación

1. Backtest con modelo ausente:
   - Verificar que `filled_qty` escala con capital y que `risk_pct_used == 2.0`.
2. Backtest con modelo presente:
   - Verificar que `risk_pct_used` cae en [1.0, 5.0] y correlaciona con `ai_prob_entry`.
3. Revisión de reports:
   - Confirmar que PnL por trade deja de ser ~1e-4 cuando el capital es 10k y el R es razonable.

