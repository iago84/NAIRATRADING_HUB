## Checklist de mejoras para subir la calidad de señales (Crypto primero)

### 1) Analítica de señales y trades (diagnóstico)
- [x] Guardar en cada trade: entry_kind, exit_reason, estado 4h/1d/1w al entrar, ATR%, distancias a EMA25/80/220, confluence, “trend_age”.
- [x] Agregar “trade analyzer”: distribución de exit_reason, PnL por exit_reason, PnL por entry_kind, PnL por régimen (ADX alto/bajo).
- [x] Medir “timing delay”: barras desde que se cumple alineación+ADX hasta que se entra (detecta señales tardías).
- [x] Medir “late entry”: distancia del precio a EMA25/80/220 y distancia a la regresión al momento de entrada.

### 2) Mejoras de timing (evitar entrar tarde)
- [x] Gating por “trend_age”: no entrar si la tendencia ya lleva N barras (p.ej. > 80 barras en 1h) sin pullback real.
- [x] Detectar “primer pullback”: permitir entrada sólo en el 1º–2º pullback tras el cruce/alineación.
- [x] Añadir confirmación de vela: rechazo (mecha) + cierre a favor + slope recupera signo.
- [x] Añadir filtro de “compresión previa”: evitar entrar cuando EMAs están demasiado expandidas (late trend).
- [x] Añadir AI gate: solo entrar si p(win) >= umbral (ai_entry_threshold).

### 3) Mejoras de ejecución (más realismo y menos DD)
- [x] Usar bar magnifier para SL/TP/BE/trailing con 5m/1m en backtests de 1h/15m.
- [x] Añadir “bar magnifier” también para la condición de entrada (timing intrabar).
- [x] Añadir spread/fees realistas por símbolo (maker/taker + slippage).

### 4) Gestión de posición (money management)
- [x] Implementar pyramiding (scale-in): serie configurable (por defecto 1-3-1-1) con límites.
- [x] Implementar anti-martingale (piramidar en wins, reducir en losses).
- [x] Implementar trailing por estructura (swing low/high) además de ATR.
- [x] Implementar “time stop”: cerrar si no progresa en N barras (reduce trades muertos).

### 5) Datos (Crypto)
- [x] Descargar 1m para los símbolos top y evaluar magnifier 1m.
- [x] Evaluar datos de trades (aggTrades) para aproximar tick-path (si es necesario).

### 6) ML / AI (mejor edge)
- [x] Ampliar features: trend_age, dist_to_ema25/80/220 en ATR, dist_to_reg_line, squeeze/expansion, slope_alignment, slope_parallelism.
- [x] Entrenar modelos por símbolo (BTC/ETH/SOL/BNB/XRP) y comparar.
- [x] Ajustar umbral de ejecución por prob(win) (no sólo blend): “solo entrar si p(win) > X”.
- [x] Evaluar calibración por bins + ECE por símbolo y por régimen (ADX alto/bajo).
- [x] Backtest tipo “robot multi-mercado”: portfolio_backtest con max_positions y selección por score.

### 7) Proceso de research (walk-forward real)
- [x] Walk-forward en ventanas temporales (train/validate) por símbolo y comparar estabilidad.
- [x] Sensibilidad (grid) incluyendo timing_timeframe, confirm_higher_tfs, slope_window, thresholds ADX/slope/alignment.
