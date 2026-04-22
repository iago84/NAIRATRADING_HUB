## Inputs fijos actuales (NAIRATRADING_HUB)

### Mercados objetivo
- Crypto: BTCUSDT
- FX/Metales (requiere MT5 en este entorno): USDJPY, XAUUSD

### Timeframes
- Base típico: 1h (o 30m/15m si se quiere más frecuencia)
- Estructura (confirmación): 4h, 1d, 1w
- Timing (ejecución): 15m (y opcionalmente 5m/1m si hay histórico)

### Features / Indicadores (core)
- EMAs: 3, 5, 10, 25, 80, 180, 220, 550, 1000
- Alineación EMA: bull/bear + ratio 0..1
- Pendiente (slope_score): cambio % medio de EMA rápidas (3/5/10/25) en ventana
- Regresión lineal (close): slope_pct y r2 en ventana
- ADX y ATR (y ATR% proxy)
- Niveles:
  - Fractals (swings) + clustering
  - Pivots diarios (P/R1/R2/R3/S1/S2/S3)
  - Fibonacci horizontal (retracements/extensions) y vertical (timezones)
  - Confluence score (niveles/pivots + fibo)
- Alligator: estado (sleeping/awakening/trend), dirección y mouth

### Parámetros (defaults de NairaConfig)
- slope_window_bars=12
- alignment_threshold=0.7
- slope_threshold_pct=0.02
- adx_length=14, adx_threshold=18
- regression_window_bars=50
- atr_length=14
- sl_atr_mult=1.2, tp_atr_mult=2.0
- min_confidence=0.55
- entry_mode="hybrid" (pullback o break&retest), entry_tol_atr=0.6
- confirm_higher_tfs=True
- timing_timeframe="15m", timing_min_confidence=0.5
- use_structure_exits=True (SL/TP pueden ajustarse por nivel/pivot cercano)
- invalidate_on_4h_flip=True
- invalidate_on_adx_ema_loss=True (ADX cae + pierde EMA25)
- partial_1r_pct=0.5, partial_2r_pct=0.25
- trailing_atr_mult=1.4 (tras 1R)
- soft_close_adx_drop=14.0
- tf_weights: 1w>1d>4h>1h>30m>15m>5m>1m

### Filtros operativos (OperationalFilterConfig)
- FX sesión UTC (por defecto 06–21)
- ATR% máximo y mínimo (proxy spread/volatilidad)
- News blackout (archivo json local)
- TTL de señal: SIGNAL_TTL_BARS (default 6)

### AI / ML (inputs del modelo actual)
- Dataset features: alignment, slope_score, regression_slope_pct, regression_r2, adx, atr, confluence_levels, confluence_fibo, alligator_mouth

### Money management (en backtest)
- sizing_mode:
  - fixed_qty (qty fijo; para BTC debe ser fraccional, no 1 BTC)
  - fixed_risk (riesgo % por trade sobre SL)
  - martingale (riesgo escalado por pérdidas; alto riesgo)
- ai_assisted_sizing: ajusta riesgo usando prob(win) del modelo (rango ai_risk_min_pct..ai_risk_max_pct)

### Bar magnifier (intra-bar)
- bar_magnifier: activa simulación intra-bar usando un TF menor
- magnifier_timeframe: TF menor (ej. 1m o 5m) usado para simular el recorrido dentro de cada vela del TF base
