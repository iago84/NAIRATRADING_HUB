import asyncio
import time
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.endpoints.health import router as health_router
from .api.v1.endpoints.naira import router as naira_router
from .api.v1.endpoints.metrics import router as metrics_router
from .core.config import settings
from .core.metrics import metrics_singleton
from .core.rate_limit import RateLimiter, RateLimitPolicy
from .services.scanner_service import scanner_singleton


app = FastAPI(title=settings.APP_NAME, version="0.1.0")
rl = RateLimiter(policy=RateLimitPolicy(per_minute=60))
scanner = scanner_singleton

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    t0 = time.time()
    rid = secrets.token_hex(8)
    metrics_singleton.rolling["requests_1m"].add()
    metrics_singleton.rolling["requests_10m"].add()
    key = request.headers.get("X-API-Key") or request.client.host if request.client else "anon"
    if not rl.allow(key):
        from fastapi.responses import JSONResponse
        metrics_singleton.rolling["errors_10m"].add()
        return JSONResponse(status_code=429, content={"detail": "rate_limited"})
    try:
        resp = await call_next(request)
    except Exception:
        metrics_singleton.rolling["errors_10m"].add()
        raise
    finally:
        dt = (time.time() - t0) * 1000.0
        metrics_singleton.add_latency(dt)
    resp.headers["X-Request-Id"] = rid
    return resp

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(naira_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "status": "ok"}


@app.on_event("startup")
async def startup_event():
    async def loop():
        while True:
            try:
                scanner.scan_once()
            except Exception:
                pass
            await asyncio.sleep(max(5, int(settings.SCAN_INTERVAL_SECONDS)))

    asyncio.create_task(loop())
