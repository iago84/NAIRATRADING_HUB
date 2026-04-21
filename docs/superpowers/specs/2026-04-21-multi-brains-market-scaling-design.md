# Diseño: Multi-cerebros + Router por régimen + Escalado por saldo (NAIRATRADING_HUB)

## Objetivo

Evolucionar NAIRATRADING_HUB desde un motor único de señales hacia un sistema:

- Multi-estrategia (varios “cerebros” de entrada/salida)
- Con selección dinámica por régimen (trend/range/transición)
- Con validación por IA (gate) que no “manda” la dirección, pero decide operar/no operar y dimensiona
- Con scanner “market-wide” que cubre múltiples mercados/timeframes y escala el universo según saldo y presupuesto de riesgo
- Con capacidad futura de ejecución automática, empezando por señales + alertas

## Principios

- Separar “generar señales” de “decidir ejecutar”.
- El sistema puede escanear muchos símbolos, pero debe ser escalable:
  - Barato primero (estructura y filtros en TF altos)
  - Caro sólo para candidatos (timing fino en TF bajos / magnifier)
- IA como validador:
  - Puede bloquear trades de baja probabilidad y ajustar sizing
  - No reemplaza reglas de estructura/entrada
- Minimizar señales contradictorias:
  - Router por régimen activa 1 cerebro dominante + opcionalmente 1 secundario
  - Agregador maneja conflicto (dominante manda)

## Alcance (fase 1 vs fase 2)

### Fase 1 (ahora)

- Backtesting multi-estrategia
- Scanner multi-mercado con escalado por saldo/risk budget
- Señales + alertas (Telegram/webhooks)
- Métricas de validación y reportes de robustez (sin optimización agresiva)

### Fase 2 (después)

- Ejecución automática (Binance + MT5)
- Sincronización de portfolio, órdenes, fills, gestión de errores
- Controles de riesgo en vivo (kill-switch, exposición, correlación, etc.)

## Arquitectura propuesta

### Componentes

1) **Universe Manager**
- Define mercados/símbolos disponibles por asset (Crypto vs FX/Metales)
- Aplica escalado por tramos (balance) y por presupuesto de riesgo

2) **Scanner Scheduler**
- Ejecuta el scan periódico por símbolo
- Estrategia por etapas:
  - Stage A: estructura (1w/1d/4h) + filtros operativos
  - Stage B: base (1h/30m) + cerebros activados por régimen
  - Stage C: timing (15m/5m/1m) sólo para top candidatos

3) **Feature Builder (multi-TF)**
- Reutiliza el pipeline actual (EMA alignment, slopes, ADX/ATR, niveles, alligator, etc.)

4) **Regime Router**
- Clasifica régimen por símbolo usando TF altos (1d/4h como mínimo):
  - Trend: ADX alto, slopes alineados, expansión EMA controlada
  - Range: ADX bajo, compresión EMA, oscilación en niveles
  - Transition: cambios de pendiente/ADX, señales mixtas
- Decide “cerebros activos”:
  - 1 dominante
  - 0..1 secundario

5) **Brains (estrategias)**
Cada cerebro implementa una interfaz común:

- input: snapshots multi-TF + contexto (símbolo, provider, TFs)
- output: SignalOut (direction/confidence/opportunity_score + reasons + risk: entry/sl/tp/ttl)

Catálogo inicial:
- **Trend-Following** (baseline): alineación EMA + slope + ADX.
- **Pullback**: trend confirmado arriba, entrada en retroceso a EMA25/80 + rechazo.
- **Breakout/Retest**: ruptura de nivel + retest con confluencia.
- **Mean-Reversion (range)**: rango (ADX bajo) y operación hacia el centro desde extremos/niveles.

6) **Aggregator (ensemble controlado)**
- Combina outputs de cerebros activos:
  - Dirección: dominante manda; secundario sólo añade confirmación/penalización.
  - Score final: suma ponderada por régimen + penalización por desacuerdo.
  - Confidence: blend y cap por tier/escala.

7) **AI Gate + AI Sizing**
- Gate: trade/no-trade por umbral de p(win) dependiente del tramo.
- Sizing: ya existe `ai_assisted_sizing`, se refuerza con “risk budget”.
- Entradas:
  - Features agregadas del snapshot
  - Features del cerebro elegido (ej. dist_ema_atr, trend_age, confluence)

8) **Risk Budget Manager**
- Budget diario/semanal por cuenta (simulado en backtest, real en vivo).
- En fase 1 afecta:
  - cuántos símbolos/timeframes se escanean
  - cuántas alertas/señales se emiten
  - cuántos trades se permiten en portfolio_backtest

9) **Notifier**
- Se reutiliza el servicio actual (Telegram + webhooks)

10) **Execution Adapter (apagado en fase 1)**
- Interfaz para Binance y MT5
- Requiere:
  - normalización de símbolos
  - tamaños mínimos/step size
  - gestión de órdenes y fills

## Escalado por saldo (4 tramos) y por asset

Umbrales iniciales (ajustables):

### Crypto (balance en USDT)
- **T0 Micro**: < 200
  - Universo: BTCUSDT, ETHUSDT
  - TFs: 4h/1d + base 1h (sin 1m/5m)
  - Router: sólo Trend + Pullback
  - AI Gate: umbral alto (estricto)
- **T1 Low**: 200–1000
  - Universo: top 10 por liquidez + BTC/ETH
  - TFs: + timing 15m
  - Router: añade Breakout/Retest
- **T2 Mid**: 1000–5000
  - Universo: top 30
  - TFs: + timing 5m
  - Se habilitan alertas más frecuentes y bar magnifier opcional
- **T3 High**: > 5000
  - Universo: top 50–100
  - TFs: + 1m y magnifier para validación intrabar en research/backtest
  - Robustez ampliada (walk-forward/threshold selection)

### FX/Metales (balance o equity base; umbral separado)
- **T0 Micro**: < 500
  - Universo: EURUSD + XAUUSD (o 1–2 símbolos)
  - TFs: 4h/1d + 1h
- **T1 Low**: 500–2000
  - Universo: FX majors + XAUUSD
  - TFs: + 15m
- **T2 Mid**: 2000–10000
  - Universo: majors + select minors + XAUUSD/XAGUSD
  - TFs: + 5m
- **T3 High**: > 10000
  - Universo: majors+minors + metales
  - TFs: + 1m donde haya datos

## Validación (qué significa “IA lo valida”)

“Validar” significa que el sistema no emite/ejecuta señales si:

- No pasa filtros operativos (sesión, ATR%, news blackout)
- El router detecta régimen incompatible con la estrategia
- El cerebro no cumple su propia condición de entrada (setup incompleto)
- El AI Gate estima p(win) por debajo del umbral del tramo

Métricas mínimas por estrategia y por régimen:
- #trades, win_rate, profit_factor, expectancy, max_drawdown
- estabilidad por régimen (trend vs range)
- sensibilidad a slippage/fees (stress test)

## Entregables (para implementación)

1) Definir interfaces:
- Brain interface (inputs/outputs)
- Router output (cerebros activos + pesos)
- Aggregator contract
- RiskBudget contract

2) Implementar cerebros adicionales y router

3) Extender scanner y portfolio_backtest para usar router+ensemble y escalado por tramo

4) Añadir reportes y tests por estrategia/régimen

