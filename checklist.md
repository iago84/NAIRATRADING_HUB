# NAIRATRADING_HUB â€” Checklist (multimercado: FX / Metales / Crypto)

## 0) DefiniciÃ³n del producto (quÃ© vendemos y a quiÃ©n)
- [x] Definir mercados objetivo: FX majors/minors (EURUSD/GBPUSD/USDJPY/AUDUSD/USDCHF/USDCAD), XAUUSD/XAGUSD, crypto spot (BTCUSDT/ETHUSDT y top caps).
- [x] Definir â€œunidad de seÃ±alâ€: SignalOut = {symbol, base_timeframe, direction, confidence, opportunity_score, risk:{entry/sl/tp/ttl/valid_until}, reasons, frames}.
- [x] Definir experiencia del usuario:
  - [x] Entrada: abrir sÃ³lo si 4h+1d (y 1w si existe) alinean + timing inferior confirma (pullback/break-retest) + filtros operativos pasan.
  - [x] GestiÃ³n: 1R mover a BE, parciales 1R/2R, trailing ATR (y/o EMA) tras 1R.
  - [x] Salida: SL/TP por ATR y/o estructura (niveles/pivots) e invalidaciÃ³n (flip 4h, ADX cae + pierde EMA, seÃ±al contraria en TF alto).
- [x] Definir monetizaciÃ³n:
  - [x] Free: seÃ±ales con retraso y sÃ³lo 4h/1d + ranking bÃ¡sico.
  - [x] Pro: seÃ±ales en tiempo real + multi-TF completo + alertas de entrada/salida.
  - [x] Trader: ejecuciÃ³n (opcional) + risk controls + stats + tuning/ML/calibraciÃ³n.

## 1) Repositorio y estructura (empezar de cero)
- [x] Crear estructura del proyecto dentro de esta carpeta (sin depender de LEGACY):
  - [x] backend/ (FastAPI) + engine/ (core de seÃ±ales/backtest) + adapters/ (providers).
  - [x] scripts/ (descargas histÃ³ricas, jobs, experimentos).
  - [x] tests/ (unit + integraciÃ³n).
- [x] Definir configuraciÃ³n por entorno (.env): secrets, providers, limits, logging, DB.
- [x] Definir contratos (schemas) de:
  - [x] SeÃ±al (SignalOut)
  - [x] Snapshot multi-TF (FrameSnapshot)
  - [x] Resultado de backtest (BacktestOut + mÃ©tricas + trades)
  - [x] Ranking/scan (lista ordenada por opportunity_score)

## 2) Datos (ingesta + normalizaciÃ³n + cachÃ©)
- [x] Normalizar OHLCV a un formato comÃºn: datetime, open, high, low, close, volume.
- [x] Providers:
  - [x] Crypto: CCXT (Binance) OHLCV, timeframes 1m/5m/15m/30m/1h/4h/1d/1w.
  - [x] FX/Metales: MT5 OHLCV (y rangos), mismos timeframes.
- [x] Persistencia histÃ³rica:
  - [x] Guardar CSV por provider/sÃ­mbolo/tf.
  - [x] ActualizaciÃ³n incremental (append/merge sin duplicados).
- [x] Cache de datos recientes:
  - [x] En memoria (MVP) + Redis opcional (producciÃ³n).
- [x] ValidaciÃ³n de calidad de datos:
  - [x] Missing bars, duplicados, timestamps fuera de orden, gaps grandes.

## 3) Features (indicadores + matemÃ¡ticas)

### 3.1 EMAs multi-escala (tu set)
- [x] EMAs: 3, 5, 10, 25, 80, 180, 220, 550, 1000 en cada TF.
- [x] AlineaciÃ³n:
  - [x] Bull: EMA3>EMA5>EMA10>EMA25>â€¦
  - [x] Bear: EMA3<EMA5<EMA10<EMA25<â€¦
  - [x] Grado de alineaciÃ³n 0..1 (pares consecutivos correctos / total).
- [x] Distancias entre EMAs:
  - [x] Spread relativo (EMA3-EMA25)/precio, (EMA25-EMA220)/precio, etc.
  - [x] CompresiÃ³n/expansiÃ³n (tendencia vs rango).

### 3.2 Pendientes y variaciones (momentum estructural)
- [x] Pendiente por EMA (regresiÃ³n o diferencia porcentual en ventana).
- [x] LÃ­nea de regresiÃ³n (close):
  - [x] Slope % (mÃ©trica de inclinaciÃ³n)
  - [x] RÂ² (calidad de ajuste)
  - [x] ProyecciÃ³n futura + distancia actual a la recta
  - [x] EstimaciÃ³n de â€œbars to reach regression lineâ€ (aprox. por velocidad)
- [x] NormalizaciÃ³n:
  - [x] Pendiente % por barra o % por N barras.
  - [x] Z-score de pendiente (por ventana) para detectar aceleraciÃ³n.
- [x] AlineaciÃ³n de pendientes:
  - [x] Pendientes rÃ¡pidas (EMA3/5/10/25) mismo signo y magnitud coherente.
  - [x] Paralelismo: |slope_ema3 - slope_ema5| pequeÃ±o + slopes altos â‡’ â€œverticalâ€.
- [x] Cambio de pendiente (curvatura):
  - [x] slope_now - slope_prev (aceleraciÃ³n/desaceleraciÃ³n).

### 3.3 Fuerza de tendencia / volatilidad
- [x] ADX (fuerza), ATR (riesgo), ATR% (volatilidad relativa).
- [x] Filtros:
  - [x] No trade en ADX bajo (rango).
  - [x] No trade en ATR% extremo (gaps/spikes) segÃºn mercado.

### 3.4 Estructura y niveles
- [x] Soportes/Resistencias:
  - [x] Swings (fractals) + clustering por tolerancia.
  - [x] Relevancia por nÃºmero de toques + distancia actual.
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
  - [x] Timezones desde los Ãºltimos 2 fractales

### 3.5 Alligator (2 o 3)
- [x] Implementar Alligator (SMMA median price + shifts).
- [x] Estado:
  - [x] â€œDormidoâ€ (mandÃ­bulas cerradas), â€œdespertandoâ€ (apertura), â€œtendenciaâ€ (apertura amplia).
- [x] IntegraciÃ³n con el scoring (no como condiciÃ³n Ãºnica).

## 4) Motor multi-timeframe (decisiÃ³n + scoring)
- [x] Definir TFs:
  - [x] Estructura: 4h obligatorio + 1d/1w si existe.
  - [x] Timing: 1m/5m/15m.
  - [x] Base: 30m o 1h (segÃºn mercado).
- [x] Scoring por TF:
  - [x] alignment_score
  - [x] slope_score
  - [x] adx_score
  - [x] volatility_penalty (ATR%)
  - [x] level_confluence_score
- [x] AgregaciÃ³n:
  - [x] PonderaciÃ³n por TF (1w>1d>4h>1h>30m>â€¦).
  - [x] Resultado final: direction, confidence, opportunity_score (0..100).
- [x] Explicabilidad:
  - [x] â€œReasonsâ€ (lista de motivos) para cada seÃ±al.
  - [x] Snapshot multi-TF (estado por TF).

## 5) Reglas de entrada (momento adecuado)
- [x] ConfirmaciÃ³n superior:
  - [x] DirecciÃ³n en 4h + 1d (y 1w si aplica).
- [x] Timing inferior:
  - [x] Pullback a EMA25/80 con rechazo (velas + slope vuelve a favor).
  - [x] Break & retest de estructura (nivel + confluencia).
- [x] Filtros operativos:
  - [x] SesiÃ³n (FX), spread (proxy ATR%), noticias (blackout local configurable).
- [x] Caducidad de la seÃ±al:
  - [x] â€œvÃ¡lida hastaâ€ (N barras) o invalidaciÃ³n por pÃ©rdida de estructura.

## 6) Reglas de salida (momento seguro)
- [x] Plan base:
  - [x] SL por ATR (o estructura), TP por ATR y/o niveles.
  - [x] 1R: mover SL a BE (o BE+offset).
  - [x] Parciales: 50% en 1R / 2R o en nivel pivot.
- [x] Invalidaciones:
  - [x] PÃ©rdida de alineaciÃ³n 4h (flip a neutral o contrario).
  - [x] CaÃ­da fuerte de ADX (tendencia se muere) + precio pierde EMA clave.
  - [x] SeÃ±al contraria confirmada en TF alto.
- [x] GestiÃ³n avanzada:
  - [x] Trailing basado en ATR o EMA (ej. trailing bajo EMA25 en buy).
  - [x] â€œSoft closeâ€ si el momentum decae (curvatura negativa + compresiÃ³n de EMAs).

## 7) Backtest y evaluaciÃ³n (Ãºltimos aÃ±os)
- [x] Backtest reproducible:
  - [x] Datos desde CSV local (primer objetivo).
  - [x] Modo â€œbar-basedâ€ con SL/TP intrabar (high/low).
- [x] MÃ©tricas mÃ­nimas:
  - [x] win_rate, profit_factor, CAGR, max_drawdown, expectancy, #trades.
- [x] Robustez:
  - [x] Walk-forward (entrena/optimiza en bloque A y valida en bloque B).
  - [x] Sensibilidad a parÃ¡metros (heatmaps).
- [x] â€œIndicadores Ã³ptimosâ€:
  - [x] Tuning de thresholds (ADX, slope_window, alignment_threshold, ATR mults, pesos TF).
  - [x] Tuning por familia de mercado (FX vs XAU vs crypto).

## 8) Escucha global del mercado (scanner)
- [x] Definir watchlist por mercado (curada).
- [x] Job de scan periÃ³dico:
  - [x] Calcula opportunity_score por sÃ­mbolo.
  - [x] Retorna Top N (y â€œwatchâ€ con cambios de estado).
- [x] RepresentaciÃ³n de oportunidades:
  - [x] â€œMapaâ€ por TF: direcciÃ³n + confianza + slope.
  - [x] Alertas por cambio de rÃ©gimen (neutralâ†’trend, trendâ†’neutral).

## 9) API y delivery de seÃ±ales
- [x] API endpoints:
  - [x] /signal (una seÃ±al detallada)
  - [x] /scan (top oportunidades)
  - [x] /backtest (ejecuta backtest con histÃ³rico local)
- [x] Seguridad:
  - [x] Auth + roles (free/pro/trader/admin).
  - [x] Rate-limit por usuario.
- [x] Notificaciones:
  - [x] Telegram: alertas (scanner) + seÃ±ales bajo demanda.
  - [x] Webhooks para integraciones.

## 10) AI / ML (cuando haya datos)
- [x] Dataset de aprendizaje:
  - [x] Features multi-TF + labels (Ã©xito por trade win/lose y pnl).
  - [x] Builder y persistencia a CSV por sÃ­mbolo/TF.
- [x] Modelos:
  - [x] Clasificador de probabilidad (P(win)) baseline (logistic regression SGD).
  - [x] CalibraciÃ³n (reliability / calibration curve).
- [x] IntegraciÃ³n:
  - [x] La IA no â€œmandaâ€; ajusta confidence (blend) y filtra seÃ±ales dudosas (por tier).

## 11) OperaciÃ³n (fiabilidad y producciÃ³n)
- [x] Logs estructurados + trazas por request (request id + mÃ©tricas).
- [x] Scheduler robusto (jobs por sÃ­mbolo/usuario).
- [x] Observabilidad:
  - [x] mÃ©tricas (latencia, errores, seÃ±ales/scans/alerts rolling).
- [x] Controles de riesgo para ejecuciÃ³n (si se activa):
  - [x] kill-switch, lÃ­mites diarios (seÃ±ales/notificaciones), cooldown.

## 12) Tests y verificaciÃ³n
- [x] Unit tests de indicadores (EMA/ATR/ADX, slopes, alineaciÃ³n).
- [x] Tests del motor multi-TF (votaciÃ³n, confluencias).
- [x] Tests del backtest (SL/TP, flips, mÃ©tricas).
- [x] Tests API (smoke con server embebido).

## 13) MigraciÃ³n desde LEGACY (sÃ³lo referencia, no dependencia)
- [x] Revisar lo ya implementado en MONEY_LEGACY/NEW_TRADING_FULL como fuente de ideas:
  - [x] data_fetchers (ccxt/mt5/csv)
  - [x] engine de backtest
  - [x] patrones de gating por suscripciÃ³n
- [x] Copiar sÃ³lo lo necesario al nuevo hub (sin arrastrar dependencias/ruido).

## 14) Operativa y Debug (rÃ¡pido)
- [x] Pipeline end-to-end (binance):
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
  - Incluir `rows` por dataset (incluye `rows=0` para ver que â€œse intentÃ³â€ en cada sÃ­mbolo/TF).
  - Entrenamiento/calibraciÃ³n deben usar sÃ³lo datasets con `rows > 0`.
- [x] AuditorÃ­a de sizing (por trade):
  - `entry_meta.risk_pct_used` y `entry_meta.sizing_mode_used` para identificar `ai_risk` vs `fixed_risk_fallback`.
- [x] â€œTP negativoâ€ / PnL raro:
  - Revisar si hubo parciales (pnl del trade final es sÃ³lo del remanente) y fees/slippage.
  - Verificar `filled_qty` y que el sizing no sea `fixed_qty=1` por fallback incorrecto.
- [x] Timing gate bloqueando demasiado:
  - Mirar `metrics.gates_timing_blocked` y el `late_entry_report.recommendations`.

## 15) Mejoras Prioritarias (prÃ³ximas)
- [x] GestiÃ³n de salida: BE + lock + trailing (sin conflicto) expresado en R/ATR.
- [x] MÃ©tricas por trade: `pnl_partials` y `pnl_total` (evitar confusiÃ³n cuando hay parciales).
- [x] â€œExplicabilidadâ€ de no-entrada: contadores por gate y por regla (para tuning rÃ¡pido).
- [x] OptimizaciÃ³n de provider/rate limits: backoff y throttling configurable en `data:update`.
- [ ] Portfolio-level backtest: equity/balance global por barra + drawdown consistente (sin signo negativo).
