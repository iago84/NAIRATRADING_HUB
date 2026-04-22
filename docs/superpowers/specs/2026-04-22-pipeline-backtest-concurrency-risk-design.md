# Diseño: Pipeline de Backtests (trades 5m), Concurrencia y Controles de Riesgo

## Contexto y Problemas

En los runs actuales bajo `backend/data/reports/...` los archivos `backtest_*_*.json` están reportando `trades: []` y `metrics.trades = 0` en múltiples timeframes (incluido `5m`). En `scripts/tasks.py`, los backtests se ejecutan con `NairaConfig(strategy_mode="multi")`, lo que fuerza `entry_mode = "regime"` dentro del backtest. El modo `regime` depende de señales/columnas que no están garantizadas en el dataframe que se pasa a las reglas de entrada, haciendo que la condición de entrada sea demasiado restrictiva y termine en 0 trades.

Además, `tasks.py all` es secuencial y tarda más de lo necesario para escaneos/backtests/datasets.

## Objetivos

1. Conseguir que los backtests (especialmente `5m`) generen trades de forma consistente y explicable.
2. Establecer un `entry_mode` general por defecto basado en `hybrid`.
3. Añadir límites de riesgo globales en backtest (y reutilizables en ejecución real) para:
   - Mantener un % de margen libre.
   - Evitar una caída del equity superior al 50% sobre el balance inicial.
4. Hacer el pipeline concurrente (más rápido) sin romper el rate limit del proveedor.
5. Enriquecer el registro y el resumen de trades para habilitar análisis posterior y un módulo de sizing asistido por AI.

## No Objetivos (por ahora)

1. Integrar feeds de noticias/calendario económico en la toma de decisiones.
2. Entrenar un modelo nuevo de sizing basado en ML en esta iteración (se prepara el dataset/telemetría para hacerlo).
3. Cambiar la lógica interna del motor de señales multi-TF más allá del ajuste de entry mode y controles de riesgo.

## Cambios Propuestos

### 1) Entry Mode: `hybrid` como default en pipeline y backtests

**Decisión:** Para el pipeline (`scripts/tasks.py`) usar `entry_mode="hybrid"` como default operativo.

**Motivación:** Desacoplar la entrada de `regime` para evitar dependencias de columnas y recuperar un flujo de trades más robusto en timeframes micro (5m/15m/30m/1h).

**Interfaz propuesta:**
- Añadir opción de ejecución:
  - CLI: `--entry-mode hybrid|pullback|break_retest|mean_reversion|regime`
  - Default: `hybrid`
- El valor se pasa al `NairaEngine(..., config=NairaConfig(strategy_mode="multi", entry_mode=<valor>))`.

### 2) Controles de Riesgo Globales en Backtest

#### 2.1 Max Drawdown (equity) vs balance inicial

**Parámetro:** `max_equity_drawdown_pct` (default: `50.0`).

**Políticas (configurables):**
- `stop_immediate` (default): termina el backtest inmediatamente.
- `stop_no_new_trades`: no abre nuevas operaciones, pero sigue avanzando barras (y gestiona cierre si hay posición).
- `stop_after_close`: no abre nuevas operaciones y termina cuando se cierra la posición abierta.

**Criterio:** si `equity <= starting_cash * (1 - max_equity_drawdown_pct/100)`.

**Salida/telemetría:**
- `metrics.risk_stop_triggered = true/false`
- `metrics.risk_stop_reason = "max_drawdown"`
- `metrics.risk_stop_policy = <policy>`
- `metrics.risk_stop_at_index`, `metrics.risk_stop_at_time`

#### 2.2 Margen libre mínimo (proxy de riesgo)

**Parámetro:** `free_cash_min_pct` (default: `0.20`).

**Definición operativa (genérica):**
- `free_cash = cash` (si el motor no modela margen/used margin explícito)
- Condición: `free_cash >= starting_cash * free_cash_min_pct`

**Políticas:** mismas que en drawdown (`stop_immediate`, `stop_no_new_trades`, `stop_after_close`).

**Salida/telemetría:**
- `metrics.free_cash_min_pct`, `metrics.free_cash_min_hit_count`

### 3) Registro y Resumen de Trades (base para “AI sizing”)

**Estado actual:** el backtest devuelve `trades[]` y `metrics` con contadores básicos.

**Ampliación propuesta (sin cambiar el contrato actual):**
- `metrics.trade_summary` con:
  - `n_trades`, `win_rate_pct`, `profit_factor`, `avg_pnl`, `avg_win`, `avg_loss`
  - `max_consecutive_wins`, `max_consecutive_losses`
  - `pnl_by_entry_kind`, `pnl_by_exit_reason`
  - `equity_curve_points` (opcional, sampleado) y `equity_min`, `equity_max`

**Export opcional:**
- Un artefacto `trades.jsonl` por backtest para análisis offline.

### 4) Concurrencia en `scripts/tasks.py`

#### 4.1 Principios
- Paralelizar por unidad de trabajo `(timeframe, symbol)` cuando los datos ya están localmente (CSV/HistoryStore).
- Controlar concurrencia y rate limit en `data:update` (Binance).
- Mantener determinismo razonable: mismos inputs deben producir mismos outputs salvo por orden de escritura (se puede estabilizar ordenando).

#### 4.2 Interfaz
- CLI: `--workers N` (default: `8`)
- CLI: `--update-workers N` (default: `2`) para `data:update` con proveedor remoto
- Opcional: `--max-inflight-requests` si se usa I/O remoto intensivo

#### 4.3 Zonas a paralelizar
- `cmd_scan`: paralelizar por símbolo dentro de cada tf (o por tf con pool por símbolo).
- `cmd_backtest_top` / `cmd_backtest_global`: paralelizar por símbolo (y/o por tf).
- `cmd_dataset_build`: paralelizar por símbolo.

#### 4.4 Escritura a disco
- Cada tarea escribe a un path único (ya ocurre), por lo que no hay colisión directa.
- Para los manifiestos (`datasets_manifest.json`), consolidar al final en un hilo.

## Compatibilidad

- Los outputs existentes (`backtest_*.json`, `scan_*.json`) se mantienen.
- Se añaden campos nuevos a `metrics` y/o artefactos opcionales sin romper el consumidor actual.

## Validación

1. Ejecutar `python scripts/tasks.py all --provider binance` con defaults.
2. Verificar que al menos un subset significativo de `backtest_5m_*.json` tenga `metrics.trades > 0`.
3. Forzar un escenario de riesgo (p.ej. parámetros agresivos) y confirmar que el backtest se corta y deja `metrics.risk_stop_*`.
4. Comparar tiempo de ejecución antes/después con `--workers` y confirmar que no hay errores de escritura ni degradación por rate limit.

## Preguntas Abiertas (para iteración futura)

1. Modelo de margen real (used margin, leverage, funding) por tipo de mercado.
2. Ingesta de noticias y calendario económico, y su correlación con símbolos/asset classes.
3. AI sizing: definición de target (max Sharpe vs max CAGR con constraints de DD) y features disponibles.

