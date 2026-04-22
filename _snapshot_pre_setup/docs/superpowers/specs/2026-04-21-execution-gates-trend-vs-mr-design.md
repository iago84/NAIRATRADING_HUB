# Diseño: Execution Gates + Separación Trend vs Mean Reversion

## Objetivo

Mejorar la calidad de señales y de entradas en backtesting (y futuro live) aplicando el mismo “contrato” de filtros/gates en:

- Señales (`/naira/signal`, `/naira/scan`, scanner_service)
- Backtests (`NairaEngine.backtest` y `portfolio_backtest` donde aplique)

El objetivo es reducir ruido y evitar “confundir rebotes con tendencia” mediante:

1) filtro estructural obligatorio
2) confluencia baja = no entrar
3) separación explícita de modos (trend vs mean reversion)
4) umbrales de ejecución más altos

## Principios

- Los gates deben ser deterministas y explicables (`reasons`).
- Una señal “final” debe representar una señal ejecutable.
- Si una condición bloquea, la salida debe ser:
  - `direction=neutral`
  - score/confidence reducidos a valores bajos y consistentes
  - reasons claros (`gate_*`)

## Variables / thresholds (defaults)

- `STRUCT_ALIGN_4H_MIN = 0.6`
- `STRUCT_ALIGN_1D_MIN = 0.6`
- `CONFLUENCE_MIN = 0.2`
- `EXEC_CONF_MIN = 0.65`
- `EXEC_ALIGN_MIN = 0.7`

Mean Reversion (MVP):
- `MR_SPREAD_FAST_PCT_MIN = 1.0` (abs)
- `MR_REQUIRE_OPPOSITE_CURVATURE = True`

## Gate 1: Filtro estructural obligatorio

Condición:

- Si `alignment(1d) < 0.6` y `alignment(4h) < 0.6` → **NO TRADE**

Implementación:

- Tomar `alignment` de `frames` para `1d` y `4h`.
- Si falta algún TF, se considera `alignment=0.0` para ese TF (conservador).

Salida:

- `direction=neutral`
- `opportunity_score=0`
- `confidence` reducido (ej. multiplicador 0.2 sobre la confianza base, cap a [0..1])
- `reasons += ["gate_structural"]`

## Gate 2: Confluencia baja (NO ENTRAR)

Condición:

- Si `level_confluence_score < 0.2` en el `base_timeframe` (fallback `4h`) → **NO TRADE**

Salida:

- `direction=neutral`
- `opportunity_score=0`
- `confidence` reducido
- `reasons += ["gate_low_confluence"]`

## Gate 3: Separación de modos (Trend vs Mean Reversion)

### Modo Trend-Following

Requisitos mínimos para que el cerebro Trend sea “ejecutable”:

- `1w.direction == 1d.direction == señal_base.direction`
- `alignment(1d) >= 0.7`
- `alignment(1w) >= 0.7` (si existe)

Si no se cumple:
- el cerebro Trend retorna neutral o queda penalizado (no puede pasar a ejecución).

### Modo Mean Reversion

Requisitos mínimos para que MR sea “ejecutable”:

- Extremo de spread en `base_timeframe`:
  - `abs(ema_spread_fast_pct) >= MR_SPREAD_FAST_PCT_MIN`
- Confirmación de giro:
  - curvatura opuesta al lado a operar (signo contrario al “impulso” actual)

Si no se cumple:
- MR no puede emitir señal ejecutable.

Router por régimen:
- `trend` → dominante `trend`, secundario `pullback`
- `range` → dominante `mean_reversion`
- `transition` → dominante `breakout`, secundario `trend`

## Gate 4: Umbral de ejecución (más alto)

Condición:

- Para ejecutar: `confidence >= 0.65` y `alignment(base_tf) >= 0.7`

Salida (si no cumple):
- `direction=neutral`
- `opportunity_score=0`
- `reasons += ["gate_execution_threshold"]`

## Observabilidad

- Cada gate añade un reason fijo.
- En `include_debug=true`, incluir valores evaluados:
  - `alignment_4h`, `alignment_1d`, `alignment_1w`
  - `level_confluence_score`
  - `exec_conf_min`, `exec_align_min`

## Pruebas mínimas

- Unit tests de gates con frames sintéticos:
  - structural gate bloquea cuando 4h+1d alignment bajo
  - low confluence gate bloquea
  - exec threshold bloquea
- Smoke test end-to-end:
  - `/naira/signal?mode=multi&include_debug=true` devuelve reasons esperados en casos forzados

