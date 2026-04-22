from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..core.config import settings


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reasons: List[str]
    debug: Dict[str, Any]


def _frames_by_tf(frames: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in frames or []:
        tf = str(f.get("timeframe") or "")
        if tf:
            out[tf] = dict(f)
    return out


def structural_gate(frames: List[Dict[str, Any]]) -> GateResult:
    by_tf = _frames_by_tf(frames)
    a4 = float((by_tf.get("4h") or {}).get("alignment") or 0.0)
    a1 = float((by_tf.get("1d") or {}).get("alignment") or 0.0)
    ok = not (a4 < float(settings.STRUCT_ALIGN_4H_MIN) and a1 < float(settings.STRUCT_ALIGN_1D_MIN))
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_structural"]), debug={"alignment_4h": a4, "alignment_1d": a1})


def confluence_gate(frames: List[Dict[str, Any]], base_timeframe: str) -> GateResult:
    by_tf = _frames_by_tf(frames)
    f = by_tf.get(str(base_timeframe)) or by_tf.get("4h") or {}
    lv = float(f.get("level_confluence_score") or 0.0)
    ok = lv >= float(settings.CONFLUENCE_MIN)
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_low_confluence"]), debug={"level_confluence_score": lv})


def execution_threshold_gate(frames: List[Dict[str, Any]], base_timeframe: str) -> GateResult:
    by_tf = _frames_by_tf(frames)
    f = by_tf.get(str(base_timeframe)) or {}
    conf = float(f.get("confidence") or 0.0)
    ali = float(f.get("alignment") or 0.0)
    ok = (conf >= float(settings.EXEC_CONF_MIN)) and (ali >= float(settings.EXEC_ALIGN_MIN))
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_execution_threshold"]), debug={"exec_conf": conf, "exec_align": ali})


def timing_gate(trend_age_bars: int, ema_compression: float) -> GateResult:
    mode = str(settings.TIMING_MODE or "expansion").lower()
    if mode == "continuation":
        max_age = int(settings.CONTINUATION_MAX_TREND_AGE)
        max_comp = float(settings.CONTINUATION_MAX_EMA_COMPRESSION)
    else:
        max_age = int(settings.EXPANSION_MAX_TREND_AGE)
        max_comp = float(settings.EXPANSION_MAX_EMA_COMPRESSION)
    reasons: List[str] = []
    if int(trend_age_bars) > int(max_age):
        reasons.append("gate_timing_age")
    if float(ema_compression) > float(max_comp):
        reasons.append("gate_timing_compression")
    ok = len(reasons) == 0
    return GateResult(
        ok=bool(ok),
        reasons=reasons,
        debug={
            "timing_mode": mode,
            "trend_age_bars": int(trend_age_bars),
            "ema_compression": float(ema_compression),
            "max_trend_age": int(max_age),
            "max_ema_compression": float(max_comp),
        },
    )
