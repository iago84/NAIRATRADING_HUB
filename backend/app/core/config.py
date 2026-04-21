import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = _env("APP_NAME", "NAIRATRADING_HUB")
    API_V1_PREFIX: str = _env("API_V1_PREFIX", "/api/v1")
    DATA_DIR: str = _env("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    DEFAULT_WATCHLIST: str = _env("DEFAULT_WATCHLIST", "")
    MAX_SCAN_SYMBOLS: int = _env_int("MAX_SCAN_SYMBOLS", 200)
    API_KEY_PRO: str = _env("API_KEY_PRO", "")
    API_KEY_TRADER: str = _env("API_KEY_TRADER", "")
    WATCHLIST_PATH: str = _env("WATCHLIST_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "data", "watchlists", "default.json"))
    SCAN_INTERVAL_SECONDS: int = _env_int("SCAN_INTERVAL_SECONDS", 60)
    SCAN_PROVIDER: str = _env("SCAN_PROVIDER", "csv")
    SCAN_BASE_TIMEFRAME: str = _env("SCAN_BASE_TIMEFRAME", "1h")
    ALERTS_MAX: int = _env_int("ALERTS_MAX", 500)
    MODELS_DIR: str = _env("MODELS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data", "models"))
    DATASETS_DIR: str = _env("DATASETS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data", "datasets"))
    NEWS_BLACKOUT_PATH: str = _env("NEWS_BLACKOUT_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "data", "news_blackout.json"))
    FX_SESSION_START_UTC: int = _env_int("FX_SESSION_START_UTC", 6)
    FX_SESSION_END_UTC: int = _env_int("FX_SESSION_END_UTC", 21)
    MAX_ATR_PCT: float = float(_env("MAX_ATR_PCT", "4.0"))
    MIN_ATR_PCT: float = float(_env("MIN_ATR_PCT", "0.02"))
    SIGNAL_TTL_BARS: int = _env_int("SIGNAL_TTL_BARS", 6)
    RISK_LIMITS_PATH: str = _env("RISK_LIMITS_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "data", "risk", "limits.json"))


settings = Settings()
