## Next improvements checklist (post quality_improvement_checklist)

### A) Research / Diagnóstico avanzado
- [x] Reporte de “late entry” por símbolo y TF (percentiles de dist_ema25_atr/dist_reg_atr) + recomendaciones automáticas de thresholds.
- [x] Breakdown por régimen (ADX/volatilidad): PF/CAGR/DD por bucket y alertas de degradación.
- [x] Validación con fees/slippage por símbolo (maker/taker + spread proxy) y stress-test de ejecución.

### B) Estrategias (combinación y régimen)
- [x] Selector de estrategia por régimen: trend-following vs mean-reversion (switch por ADX + compresión + pendiente).
- [x] Señales combinadas: score ensemble (EMA alignment + regression + levels + alligator) con pesos entrenables.
- [x] “No late trend”: filtro por expansión + distancia a EMA/regresión + trend_age adaptativo por TF.

### C) Ejecución (intra-bar mejorada)
- [x] Bar magnifier para entrada usando 1m + lógica de “primer toque/retest” con microestructura simple.
- [x] Modelo de fill: partial fills + slippage dependiente de ATR% + tamaño (impacto simplificado).
- [x] Integración opcional de aggTrades para tick-path (crypto) y comparación contra OHLC 1m.

### D) Money management avanzado
- [x] Pyramiding por estructura: añadir sólo en “retests” confirmados (no en continuación ciega).
- [x] Portfolio risk: límite de exposición total, correlación, max concurrent por sector (L1/L2 caps).
- [x] Position sizing por volatilidad (vol targeting) y Kelly fraccional con cap por drawdown.

### E) ML / AI
- [x] Modelos por símbolo + meta-model (stacking) que decida “trade/no trade” y sizing.
- [x] Walk-forward con selección de umbral p(win) por fold (optimize threshold).
- [x] Features nuevas: slope_z/curvature, slope_alignment/parallelism, session flags, distance-to-level/pivot.

### F) Operación multi-mercado
- [x] Portfolio_backtest con capital compartido + cola de señales (prioridad por score) + cooldown global.
- [x] Scanner multi-símbolo con ranking estable (histeresis) para evitar “flapping”.
