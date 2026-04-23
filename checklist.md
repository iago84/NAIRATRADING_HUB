# NAIRATRADING_HUB — Checklist (multimercado: FX / Metales / Crypto)

## 0) Definición del producto (qué vendemos y a quién)
- [x] Definir mercados objetivo: FX majors/minors (EURUSD/GBPUSD/USDJPY/AUDUSD/USDCHF/USDCAD), XAUUSD/XAGUSD, crypto spot (BTCUSDT/ETHUSDT y top caps).
- [x] Definir “unidad de señal”: SignalOut = {symbol, base_timeframe, direction, confidence, opportunity_score, risk:{entry/sl/tp/ttl/valid_until}, reasons, frames}.
- [x] Definir experiencia del usuario:
  - [x] Entrada: abrir sólo si 4h+1d (y 1w si existe) alinean + timing inferior confirma (pullback/break-retest) + filtros operativos pasan.
  - [x] Gestión: 1R mover a BE, parciales 1R/2R, trailing ATR (y/o EMA) tras 1R.
  - [x] Salida: SL/TP por ATR y/o estructura (niveles/pivots) e invalidación (flip 4h, ADX cae + pierde EMA, señal contraria en TF alto).
- [x] Definir monetización:
  - [x] Free: señales con retraso y sólo 4h/1d + ranking básico.
  - [x] Pro: señales en tiempo real + multi-TF completo + alertas de entrada/salida.
  - [x] Trader: ejecución (opcional) + risk controls + stats + tuning/ML/calibración.

## 1) Repositorio y estructura (empezar de cero)
- [x] Crear estructura del proyecto dentro de esta carpeta (sin depender de LEGACY):
  - [x] backend/ (FastAPI) + engine/ (core de señales/backtest) + adapters/ (providers).
  - [x] scripts/ (descargas históricas, jobs, experimentos).
  - [x] tests/ (unit + integración).
- [x] Definir configuración por entorno (.env): secrets, providers, limits, logging, DB.
- [x] Definir contratos (schemas) de:
  - [x] Señal (SignalOut)
  - [x] Snapshot multi-TF (FrameSnapshot)
  - [x] Resultado de backtest (BacktestOut + métricas + trades)
  - [x] Ranking/scan (lista ordenada por opportunity_score)

## 2) Datos (ingesta + normalización + caché)
- [x] Normalizar OHLCV a un formato común: datetime, open, high, low, close, volume.
- [x] Providers:
  - [x] Crypto: CCXT (Binance) OHLCV, timeframes 1m/5m/15m/30m/1h/4h/1d/1w.
  - [x] FX/Metales: MT5 OHLCV (y rangos), mismos timeframes.
- [x] Persistencia histórica:
  - [x] Guardar CSV por provider/símbolo/tf.
  - [x] Actualización incremental (append/merge sin duplicados).
- [x] Cache de datos recientes:
  - [x] En memoria (MVP) + Redis opcional (producción).
- [x] Validación de calidad de datos:
  - [x] Missing bars, duplicados, timestamps fuera de orden, gaps grandes.

## 3) Features (indicadores + matemáticas)

### 3.1 EMAs multi-escala (tu set)
- [x] EMAs: 3, 5, 10, 25, 80, 180, 220, 550, 1000 en cada TF.
- [x] Alineación:
  - [x] Bull: EMA3>EMA5>EMA10>EMA25>…
  - [x] Bear: EMA3<EMA5<EMA10<EMA25<…
  - [x] Grado de alineación 0..1 (pares consecutivos correctos / total).
- [x] Distancias entre EMAs:
  - [x] Spread relativo (EMA3-EMA25)/precio, (EMA25-EMA220)/precio, etc.
  - [x] Compresión/expansión (tendencia vs rango).

### 3.2 Pendientes y variaciones (momentum estructural)
- [x] Pendiente por EMA (regresión o diferencia porcentual en ventana).
- [x] Línea de regresión (close):
  - [x] Slope % (métrica de inclinación)
  - [x] R² (calidad de ajuste)
  - [x] Proyección futura + distancia actual a la recta
  - [x] Estimación de “bars to reach regression line” (aprox. por velocidad)
- [x] Normalización:
  - [x] Pendiente % por barra o % por N barras.
  - [x] Z-score de pendiente (por ventana) para detectar aceleración.
- [x] Alineación de pendientes:
  - [x] Pendientes rápidas (EMA3/5/10/25) mismo signo y magnitud coherente.
  - [x] Paralelismo: |slope_ema3 - slope_ema5| pequeño + slopes altos ⇒ “vertical”.
- [x] Cambio de pendiente (curvatura):
  - [x] slope_now - slope_prev (aceleración/desaceleración).

### 3.3 Fuerza de tendencia / volatilidad
- [x] ADX (fuerza), ATR (riesgo), ATR% (volatilidad relativa).
- [x] Filtros:
  - [x] No trade en ADX bajo (rango).
  - [x] No trade en ATR% extremo (gaps/spikes) según mercado.

### 3.4 Estructura y niveles
- [x] Soportes/Resistencias:
  - [x] Swings (fractals) + clustering por tolerancia.
  - [x] Relevancia por número de toques + distancia actual.
- [x] Pivots:
  - [x] Diarios (P/R1/R2/R3/S1/S2/S3) + confluencia con EMAs.
- [x] Confluencias:
  - [x] Nivel cercano + EMA clave + TF alto alineado.
- [x] Relevancia de niveles:
  - [x] Touches (conteo de toques por tolerancia)
  - [x] Distancia normalizada por ATR (distance_atr)
- [x] Fibonacci horizontal:
  - [x] Retracements/Extensions calculados desde rango (lookback)
  - [x] Confluence score por proximidad a niveles
- [x] Fibonacci vertical:
  - [x] Timezones desde los últimos 2 fractales

### 3.5 Alligator (2 o 3)
- [x] Implementar Alligator (SMMA median price + shifts).
- [x] Estado:
  - [x] “Dormido” (mandíbulas cerradas), “despertando” (apertura), “tendencia” (apertura amplia).
- [x] Integración con el scoring (no como condición única).

## 4) Motor multi-timeframe (decisión + scoring)
- [x] Definir TFs:
  - [x] Estructura: 4h obligatorio + 1d/1w si existe.
  - [x] Timing: 1m/5m/15m.
  - [x] Base: 30m o 1h (según mercado).
- [x] Scoring por TF:
  - [x] alignment_score
  - [x] slope_score
  - [x] adx_score
  - [x] volatility_penalty (ATR%)
  - [x] level_confluence_score
- [x] Agregación:
  - [x] Ponderación por TF (1w>1d>4h>1h>30m>…).
  - [x] Resultado final: direction, confidence, opportunity_score (0..100).
- [x] Explicabilidad:
  - [x] “Reasons” (lista de motivos) para cada señal.
  - [x] Snapshot multi-TF (estado por TF).

## 5) Reglas de entrada (momento adecuado)
- [x] Confirmación superior:
  - [x] Dirección en 4h + 1d (y 1w si aplica).
- [x] Timing inferior:
  - [x] Pullback a EMA25/80 con rechazo (velas + slope vuelve a favor).
  - [x] Break & retest de estructura (nivel + confluencia).
- [x] Filtros operativos:
  - [x] Sesión (FX), spread (proxy ATR%), noticias (blackout local configurable).
- [x] Caducidad de la señal:
  - [x] “válida hasta” (N barras) o invalidación por pérdida de estructura.

## 6) Reglas de salida (momento seguro)
- [x] Plan base:
  - [x] SL por ATR (o estructura), TP por ATR y/o niveles.
  - [x] 1R: mover SL a BE (o BE+offset).
  - [x] Parciales: 50% en 1R / 2R o en nivel pivot.
- [x] Invalidaciones:
  - [x] Pérdida de alineación 4h (flip a neutral o contrario).
  - [x] Caída fuerte de ADX (tendencia se muere) + precio pierde EMA clave.
  - [x] Señal contraria confirmada en TF alto.
- [x] Gestión avanzada:
  - [x] Trailing basado en ATR o EMA (ej. trailing bajo EMA25 en buy).
  - [x] “Soft close” si el momentum decae (curvatura negativa + compresión de EMAs).

## 7) Backtest y evaluación (últimos años)
- [x] Backtest reproducible:
  - [x] Datos desde CSV local (primer objetivo).
  - [x] Modo “bar-based” con SL/TP intrabar (high/low).
- [x] Métricas mínimas:
  - [x] win_rate, profit_factor, CAGR, max_drawdown, expectancy, #trades.
- [x] Robustez:
  - [x] Walk-forward (entrena/optimiza en bloque A y valida en bloque B).
  - [x] Sensibilidad a parámetros (heatmaps).
- [x] “Indicadores óptimos”:
  - [x] Tuning de thresholds (ADX, slope_window, alignment_threshold, ATR mults, pesos TF).
  - [x] Tuning por familia de mercado (FX vs XAU vs crypto).

## 8) Escucha global del mercado (scanner)
- [x] Definir watchlist por mercado (curada).
- [x] Job de scan periódico:
  - [x] Calcula opportunity_score por símbolo.
  - [x] Retorna Top N (y “watch” con cambios de estado).
- [x] Representación de oportunidades:
  - [x] “Mapa” por TF: dirección + confianza + slope.
  - [x] Alertas por cambio de régimen (neutral→trend, trend→neutral).

## 9) API y delivery de señales
- [x] API endpoints:
  - [x] /signal (una señal detallada)
  - [x] /scan (top oportunidades)
  - [x] /backtest (ejecuta backtest con histórico local)
- [x] Seguridad:
  - [x] Auth + roles (free/pro/trader/admin).
  - [x] Rate-limit por usuario.
- [x] Notificaciones:
  - [x] Telegram: alertas (scanner) + señales bajo demanda.
  - [x] Webhooks para integraciones.

## 10) AI / ML (cuando haya datos)
- [x] Dataset de aprendizaje:
  - [x] Features multi-TF + labels (éxito por trade win/lose y pnl).
  - [x] Builder y persistencia a CSV por símbolo/TF.
- [x] Modelos:
  - [x] Clasificador de probabilidad (P(win)) baseline (logistic regression SGD).
  - [x] Calibración (reliability / calibration curve).
- [x] Integración:
  - [x] La IA no “manda”; ajusta confidence (blend) y filtra señales dudosas (por tier).

## 11) Operación (fiabilidad y producción)
- [x] Logs estructurados + trazas por request (request id + métricas).
- [x] Scheduler robusto (jobs por símbolo/usuario).
- [x] Observabilidad:
  - [x] métricas (latencia, errores, señales/scans/alerts rolling).
- [x] Controles de riesgo para ejecución (si se activa):
  - [x] kill-switch, límites diarios (señales/notificaciones), cooldown.

## 12) Tests y verificación
- [x] Unit tests de indicadores (EMA/ATR/ADX, slopes, alineación).
- [x] Tests del motor multi-TF (votación, confluencias).
- [x] Tests del backtest (SL/TP, flips, métricas).
- [x] Tests API (smoke con server embebido).

## 13) Migración desde LEGACY (sólo referencia, no dependencia)
- [x] Revisar lo ya implementado en MONEY_LEGACY/NEW_TRADING_FULL como fuente de ideas:
  - [x] data_fetchers (ccxt/mt5/csv)
  - [x] engine de backtest
  - [x] patrones de gating por suscripción
- [x] Copiar sólo lo necesario al nuevo hub (sin arrastrar dependencias/ruido).

## 14) Operativa y Debug (rápido)
- [ ] Pipeline end-to-end (binance):
  - `python scripts/tasks.py all --provider binance --workers 8 --update-workers 2`
- [x] Flags clave del pipeline:
  - `--entry-mode` (default: hybrid)
  - `--sizing-mode` (default: ai_risk)
  - `--risk-per-trade-pct` (fallback fixed_risk, default: 2.0)
  - `--ai-risk-min-pct/--ai-risk-max-pct` (default: 1.0/5.0)
  - `--max-equity-drawdown-pct/--free-cash-min-pct/--risk-stop-policy`
- [x] Artefactos por run:
  - `scan_<tf>.json`, `backtest_<tf>_<sym>.json`, `datasets_manifest.json`, `setup_edge.json/.md/.html`, `train.json`, `calibration.json`
- [x] Datasets manifest:
  - Incluir `rows` por dataset (incluye `rows=0` para ver que “se intentó” en cada símbolo/TF).
  - Entrenamiento/calibración deben usar sólo datasets con `rows > 0`.
- [x] Auditoría de sizing (por trade):
  - `entry_meta.risk_pct_used` y `entry_meta.sizing_mode_used` para identificar `ai_risk` vs `fixed_risk_fallback`.
- [x] “TP negativo” / PnL raro:
  - Revisar si hubo parciales (pnl del trade final es sólo del remanente) y fees/slippage.
  - Verificar `filled_qty` y que el sizing no sea `fixed_qty=1` por fallback incorrecto.
- [x] Timing gate bloqueando demasiado:
  - Mirar `metrics.gates_timing_blocked` y el `late_entry_report.recommendations`.

## 15) Mejoras Prioritarias (próximas)
- [x] Gestión de salida: BE + lock + trailing (sin conflicto) expresado en R/ATR.
- [x] Métricas por trade: `pnl_partials` y `pnl_total` (evitar confusión cuando hay parciales).
- [x] “Explicabilidad” de no-entrada: contadores por gate y por regla (para tuning rápido).
- [x] Optimización de provider/rate limits: backoff y throttling configurable en `data:update`.
- [x] Portfolio-level backtest: equity/balance global por barra + drawdown consistente (sin signo negativo).
