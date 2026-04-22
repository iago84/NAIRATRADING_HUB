# NAIRATRADING_HUB

Backend (FastAPI) + motor de señales/backtesting multi-timeframe para FX/Metales/Crypto.

## Requisitos

- Python 3.10+ (recomendado 3.11/3.12)

## Instalación

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Extras (providers/caché):

```bash
pip install -r backend/requirements-extras.txt
```

## Configuración

Copiar variables de entorno:

```bash
cp .env.example .env
```

Variables principales:

- DATA_DIR (por defecto backend/data)
- SCAN_PROVIDER (csv|binance|ccxt|mt5)
- SCAN_BASE_TIMEFRAME (por defecto 1h)
- BALANCE_USDT (para escalar el universo en /scan y el AI gate)
- CRYPTO_T0_MAX/CRYPTO_T1_MAX/CRYPTO_T2_MAX (tramos crypto)
- FX_T0_MAX/FX_T1_MAX/FX_T2_MAX (tramos FX/metales)
- AI_GATE_T0..AI_GATE_T3 (umbral p(win) por tramo)
- STRUCT_ALIGN_4H_MIN/STRUCT_ALIGN_1D_MIN (filtro estructural obligatorio)
- CONFLUENCE_MIN (confluencia mínima; por debajo no entra)
- EXEC_CONF_MIN/EXEC_ALIGN_MIN (umbral de ejecución)
- MR_SPREAD_FAST_PCT_MIN/MR_REQUIRE_OPPOSITE_CURVATURE (requisitos MR)
- API_KEY_PRO / API_KEY_TRADER (tiers)
- REDIS_URL (opcional, cache)
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / WEBHOOK_URLS (notificaciones)

## Ejecutar la API

```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Healthcheck:

- GET /api/v1/health

## Endpoints principales (API v1)

- GET /api/v1/naira/signal
- GET /api/v1/naira/scan
- POST /api/v1/naira/backtest
- POST /api/v1/naira/portfolio/backtest (requiere X-API-Key tier TRADER)
- GET/PUT /api/v1/naira/watchlist (PUT requiere TRADER)
- GET /api/v1/naira/scan/status
- GET /api/v1/naira/alerts
- POST /api/v1/naira/tune (TRADER)
- POST /api/v1/naira/dataset/build (TRADER)
- POST /api/v1/naira/model/train (TRADER)
- POST /api/v1/naira/model/calibrate (TRADER)
- POST /api/v1/naira/robustness/* (TRADER)

Parámetros útiles:

- `/naira/signal`: `mode=single|multi`, `balance_usdt`, `asset=crypto|fx|metals`, `include_debug`
- `/naira/scan`: `mode=single|multi`, `balance_usdt`, `asset=crypto|fx|metals|all`, `top`

## Tests

```bash
cd backend
pytest -q
```

## Scripts útiles

- scripts/scan_job.py
- scripts/download_history.py
- scripts/bulk_download.py
- scripts/random_backtests.py
