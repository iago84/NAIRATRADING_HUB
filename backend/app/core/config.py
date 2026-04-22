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
    BALANCE_USDT: float = float(_env("BALANCE_USDT", "0"))

    CRYPTO_T0_MAX: float = float(_env("CRYPTO_T0_MAX", "200"))
    CRYPTO_T1_MAX: float = float(_env("CRYPTO_T1_MAX", "1000"))
    CRYPTO_T2_MAX: float = float(_env("CRYPTO_T2_MAX", "5000"))

    FX_T0_MAX: float = float(_env("FX_T0_MAX", "500"))
    FX_T1_MAX: float = float(_env("FX_T1_MAX", "2000"))
    FX_T2_MAX: float = float(_env("FX_T2_MAX", "10000"))

    AI_GATE_T0: float = float(_env("AI_GATE_T0", "0.62"))
    AI_GATE_T1: float = float(_env("AI_GATE_T1", "0.58"))
    AI_GATE_T2: float = float(_env("AI_GATE_T2", "0.54"))
    AI_GATE_T3: float = float(_env("AI_GATE_T3", "0.50"))

    STRUCT_ALIGN_4H_MIN: float = float(_env("STRUCT_ALIGN_4H_MIN", "0.55"))
    STRUCT_ALIGN_1D_MIN: float = float(_env("STRUCT_ALIGN_1D_MIN", "0.55"))
    CONFLUENCE_MIN: float = float(_env("CONFLUENCE_MIN", "0.15"))
    EXEC_CONF_MIN: float = float(_env("EXEC_CONF_MIN", "0.60"))
    EXEC_ALIGN_MIN: float = float(_env("EXEC_ALIGN_MIN", "0.65"))
    MICRO_TFS: str = _env("MICRO_TFS", "5m,15m,30m")
    CONFLUENCE_MIN_MICRO: float = float(_env("CONFLUENCE_MIN_MICRO", "0.10"))
    EXEC_CONF_MIN_MICRO: float = float(_env("EXEC_CONF_MIN_MICRO", "0.55"))
    EXEC_ALIGN_MIN_MICRO: float = float(_env("EXEC_ALIGN_MIN_MICRO", "0.60"))

    MR_SPREAD_FAST_PCT_MIN: float = float(_env("MR_SPREAD_FAST_PCT_MIN", "1.0"))
    MR_REQUIRE_OPPOSITE_CURVATURE: int = _env_int("MR_REQUIRE_OPPOSITE_CURVATURE", 1)

    TIMING_MODE: str = _env("TIMING_MODE", "expansion").strip().lower()
    EXPANSION_MAX_TREND_AGE: int = _env_int("EXPANSION_MAX_TREND_AGE", 3)
    EXPANSION_MAX_EMA_COMPRESSION: float = float(_env("EXPANSION_MAX_EMA_COMPRESSION", "2.0"))
    EXPANSION_MAX_TREND_AGE_MICRO: int = _env_int("EXPANSION_MAX_TREND_AGE_MICRO", 4)
    EXPANSION_MAX_EMA_COMPRESSION_MICRO: float = float(_env("EXPANSION_MAX_EMA_COMPRESSION_MICRO", "2.5"))
    CONTINUATION_MAX_TREND_AGE: int = _env_int("CONTINUATION_MAX_TREND_AGE", 8)
    CONTINUATION_MAX_EMA_COMPRESSION: float = float(_env("CONTINUATION_MAX_EMA_COMPRESSION", "5.0"))


settings = Settings()
