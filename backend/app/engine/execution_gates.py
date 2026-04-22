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


def _is_micro_tf(base_timeframe: str) -> bool:
    micro = [s.strip() for s in str(settings.MICRO_TFS or "").split(",") if s.strip()]
    return str(base_timeframe) in set(micro)


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
    thr = float(settings.CONFLUENCE_MIN_MICRO) if _is_micro_tf(base_timeframe) else float(settings.CONFLUENCE_MIN)
    ok = lv >= float(thr)
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_low_confluence"]), debug={"level_confluence_score": lv, "min": float(thr)})


def execution_threshold_gate(frames: List[Dict[str, Any]], base_timeframe: str) -> GateResult:
    by_tf = _frames_by_tf(frames)
    f = by_tf.get(str(base_timeframe)) or {}
    conf = float(f.get("confidence") or 0.0)
    ali = float(f.get("alignment") or 0.0)
    thr_conf = float(settings.EXEC_CONF_MIN_MICRO) if _is_micro_tf(base_timeframe) else float(settings.EXEC_CONF_MIN)
    thr_ali = float(settings.EXEC_ALIGN_MIN_MICRO) if _is_micro_tf(base_timeframe) else float(settings.EXEC_ALIGN_MIN)
    ok = (conf >= float(thr_conf)) and (ali >= float(thr_ali))
    return GateResult(ok=bool(ok), reasons=([] if ok else ["gate_execution_threshold"]), debug={"exec_conf": conf, "exec_align": ali, "min_conf": float(thr_conf), "min_align": float(thr_ali)})


def timing_gate(trend_age_bars: int, ema_compression: float, base_timeframe: str = "") -> GateResult:
    mode = str(settings.TIMING_MODE or "expansion").lower()
    if mode == "continuation":
        max_age = int(settings.CONTINUATION_MAX_TREND_AGE)
        max_comp = float(settings.CONTINUATION_MAX_EMA_COMPRESSION)
    else:
        if _is_micro_tf(base_timeframe):
            max_age = int(settings.EXPANSION_MAX_TREND_AGE_MICRO)
            max_comp = float(settings.EXPANSION_MAX_EMA_COMPRESSION_MICRO)
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
            "base_timeframe": str(base_timeframe),
        },
    )
