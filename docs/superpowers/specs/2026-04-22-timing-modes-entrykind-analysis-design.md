# Diseño: Timing Modes (EXPANSIÓN) + Entry Kind + Analyzer (scan_job/random_backtests)

## Objetivo

Convertir el “timing” en regla dura, separando explícitamente modos de mercado y dejando trazabilidad del tipo de entrada (setup) para poder optimizar:

- Señales/scan: solo emitir señales ejecutables cuando cumplen timing.
- Backtest: bloquear entradas tardías/defectuosas con la misma regla.
- Análisis: generar reportes automáticos de `scan_job.py` y `random_backtests.py` con buckets por timing y por `entry_kind`.

## Contexto actual (repo)

- Backtest ya calcula `trend_age_bars` y usa `ema_compression`.
- `entry_rules.decide_entry(...)` ya devuelve `EntryDecision(kind=...)` (`pullback`, `break_retest`, `mean_reversion`, `hybrid`, `regime`, `none`).
- Hay gates de ejecución recientes:
  - `gate_structural` (alignment 4h/1d)
  - `gate_low_confluence`
  - `gate_execution_threshold`

Este diseño añade:

1) **gate_timing** con presets “expansion” y “continuation”
2) **exposición consistente de `entry_kind`** (señales y trades)
3) **analyzer** para resultados de scan/backtests

## Timing Modes

Se introduce una variable (env/config):

- `TIMING_MODE = expansion | continuation` (default: `expansion`)

### Preset EXPANSIÓN (default)

Regla dura (NO TRADE):

- Si `trend_age_bars > 2` → bloquear
- Si `ema_compression > 1.5` → bloquear

Interpretación:
- El edge está en inicio de movimiento + baja compresión (eventos raros pero limpios).

### Preset CONTINUACIÓN (experimental)

Regla dura (NO TRADE):

- Si `trend_age_bars > 8` → bloquear
- Si `ema_compression > 5.0` → bloquear

Interpretación:
- Mantiene compatibilidad con el comportamiento actual, pero deja espacio para lógica distinta futura.

## Implementación: Gate de timing (común)

Se añade a `execution_gates.py`:

- `timing_gate(trend_age_bars: int, ema_compression: float) -> GateResult`

Reasons:
- `gate_timing_age`
- `gate_timing_compression`

Debug mínimo:
- `timing_mode`, `trend_age_bars`, `ema_compression`, `max_trend_age`, `max_ema_compression`

## Cómo obtener trend_age/ema_compression en señales (analyze/scan)

Para señales, se necesita garantizar que `frames` incluyan:

- `ema_compression` (ya existe)
- `trend_age_bars` (añadirlo al frame base)

Definición de `trend_age_bars` (señales):
- Basado en la serie de `direction` del frame base: “cuántas velas consecutivas lleva la dirección actual sin cambiar”.
- Debe coincidir con la lógica del backtest para consistencia.

## Entry Kind (tipología de entrada)

Objetivo: evitar `entry_kind_counts: {"none": ...}` como “caja negra”.

### Señales/scan

La señal final debe incluir el `entry_kind` que justifica la entrada:

- `trend/pullback`: `pullback` o `break_retest` según `decide_entry(..., mode="hybrid")`
- `breakout`: `break_retest`
- `mean_reversion`: `mean_reversion`

Además:
- En `include_debug=true`, incluir `entry_decision.details`.

### Backtest

Cada trade debe tener `entry_kind` (ya existe en trades) y debe ser consistente con el modo de entrada elegido:

- Si `TIMING_MODE=expansion` bloquea, no hay trade.
- Si entra: `entry_kind` debe venir de `decide_entry` (`ed.kind`).

## Analyzer: resultados de scan_job y random_backtests

Se crea un script único:

- `scripts/analyze_runs.py`

Entradas:

1) `--scan-json <path>`: JSON array (salida de `scan_job.py`)
2) `--random-jsonl <path>`: JSONL (salida de `random_backtests.py`)

Salidas:

- `--out-md <path>`: reporte Markdown
- (opcional) `--out-json <path>`: métricas estructuradas para consumo por LLM (GPT)

Métricas clave:
- Señales (scan):
  - distribución por `direction`, `brain`, `entry_kind`
  - buckets por `trend_age_bars` y `ema_compression`
  - conteo de bloqueos por gate (si viene en debug)
- Backtests (random):
  - expectancy por trade (si hay `avg_pnl_per_trade`, `trades`, etc. en `metrics`)
  - distribución de métricas por buckets (trend_age/comp si se registran)

## Testing mínimo

- Unit test de `timing_gate` con ambos presets
- Unit test de parser de `analyze_runs.py` con fixtures pequeñas

