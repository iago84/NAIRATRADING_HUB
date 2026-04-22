from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional


Direction = Literal["buy", "sell", "neutral"]


class FrameSnapshot(BaseModel):
    timeframe: str
    direction: Direction
    alignment: float
    slope_score: float
    regression_slope_pct: Optional[float] = None
    regression_r2: Optional[float] = None
    slope_z: Optional[float] = None
    curvature: Optional[float] = None
    slope_alignment: Optional[float] = None
    slope_parallelism: Optional[float] = None
    ema_spread_fast_pct: Optional[float] = None
    ema_spread_trend_pct: Optional[float] = None
    ema_compression: Optional[float] = None
    adx: Optional[float] = None
    atr: Optional[float] = None
    adx_score: Optional[float] = None
    atr_pct: Optional[float] = None
    volatility_penalty: Optional[float] = None
    level_confluence_score: Optional[float] = None
    confidence: float


class RiskPlan(BaseModel):
    entry_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    atr: Optional[float] = None
    risk_r: Optional[float] = None
    safe_exit_hint: Optional[str] = None
    valid_until: Optional[str] = None
    ttl_bars: Optional[int] = None


class SignalOut(BaseModel):
    timestamp: str
    symbol: str
    provider: str
    base_timeframe: str
    direction: Direction
    confidence: float
    opportunity_score: float
    price: float
    frames: List[FrameSnapshot]
    reasons: List[str]
    risk: RiskPlan
    debug: Optional[Dict[str, Any]] = None


class BacktestTrade(BaseModel):
    side: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    pnl: float
    bars_held: int
    entry_kind: Optional[str] = None
    exit_reason: Optional[str] = None
    entry_sub_index: Optional[int] = None
    entry_meta: Optional[Dict[str, Any]] = None


class BacktestOut(BaseModel):
    symbol: str
    provider: str
    base_timeframe: str
    start: str
    end: str
    metrics: Dict[str, Any]
    trades: List[BacktestTrade]
