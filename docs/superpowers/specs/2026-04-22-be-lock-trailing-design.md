# Diseño: BE por R + Lock + Trailing sin conflicto

## Objetivo

Reducir trades de PnL ~0.0 por breakeven puro, añadiendo un esquema de gestión de SL en 2 pasos, expresado en fracción de R (distancia entry→SL inicial), y coordinado con el trailing para que no se “pise” (nunca empeore el SL).

## Estado actual

En `NairaEngine.backtest`:

1. SL/TP inicial se fijan por ATR (`sl_atr_mult`, `tp_atr_mult`), con ajustes opcionales por estructura.
2. Breakeven: cuando el precio avanza +1R, se mueve `SL = entry` (flag `be_done`).
3. Parciales: se ejecutan en +1R y +2R (y reducen `qty`).
4. Trailing: se activa tras el primer parcial (`p1_done`) y actualiza SL usando `max/min` (no reduce el SL).

Resultado: en condiciones laterales, es común ver trades cerrados en `SL=entry` (PnL 0.0 si fees/slippage son 0).

## Cambio propuesto (Opción C acordada)

Se añade un segundo escalón tras el BE para asegurar un “lock” mínimo de beneficio antes de activar trailing:

### Parámetros (defaults)

- `be_trigger_r = 1.0`
  - Cuando el movimiento a favor alcanza 1.0R, se mueve `SL = entry` (BE clásico).
- `trail_trigger_r = 1.5`
  - Cuando el movimiento a favor alcanza 1.5R, se activa trailing.
- `lock_r = 0.10`
  - En el momento de activar trailing (>= 1.5R), se fuerza un SL mínimo:
    - Buy: `SL >= entry + lock_r * R`
    - Sell: `SL <= entry - lock_r * R`

### Reglas de interacción (no pisarse)

Orden de aplicación por barra (si hay posición):

1. Calcular `R = abs(entry - SL_inicial)` (o `abs(entry - sl_actual)` si se mantiene constante tras set inicial).
2. Aplicar BE si aún no se aplicó y movimiento >= `be_trigger_r * R`.
3. Si movimiento >= `trail_trigger_r * R`:
   - Aplicar lock mínimo (`entry ± lock_r * R`).
   - Aplicar trailing ATR (`trailing_atr_mult * ATR`) y combinar con lock usando `max/min`:
     - Buy: `SL = max(SL, lock_sl, trail_sl)`
     - Sell: `SL = min(SL, lock_sl, trail_sl)`

Propiedad clave: el SL solo mejora en la dirección de protección; nunca retrocede.

## Salida / observabilidad (opcional)

Agregar a `entry_meta` o `trade.exit_reason` señales como:
- `be_applied=true`, `be_lock_applied=true`
- `sl_mode` en cada trade: `atr`, `structure`, `be`, `lock`, `trailing`

(No es obligatorio para el primer cambio, pero ayuda a depurar).

## Validación

1. Unit test: simular una secuencia de precios donde:
   - se activa BE en 1R,
   - luego se activa lock en 1.5R,
   - y trailing no reduce el SL.
2. Smoke test en backtest 5m: verificar reducción de `pnl == 0.0` cuando antes predominaba BE puro (no garantizado en todos los símbolos, pero debería bajar en promedio).

