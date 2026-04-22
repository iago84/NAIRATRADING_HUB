from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.logger import get_logger
from ..core.metrics import metrics_singleton
from ..engine.naira_engine import NairaEngine
from ..engine.watchlist import WatchlistStore
from ..engine.universe import UniverseManager, tranche_for_balance
from ..engine.filters import classify_symbol
from ..engine.multi_brain import run_multi_brain
from .notifier_service import notifier_singleton


@dataclass
class ScanStatus:
    last_run_ts: int = 0
    last_duration_ms: int = 0
    last_error: Optional[str] = None
    last_top: Optional[List[Dict[str, Any]]] = None


class ScannerService:
    def __init__(self):
        self.logger = get_logger("scanner")
        self.engine = NairaEngine(data_dir=settings.DATA_DIR)
        self.watchlist = WatchlistStore(path=settings.WATCHLIST_PATH)
        self._last_dir: Dict[str, str] = {}
        self._last_score: Dict[str, float] = {}
        self._alerts: List[Dict[str, Any]] = []
        self.status = ScanStatus()
        self.events_path = os.path.join(settings.DATA_DIR, "events", "scanner_events.jsonl")
        self.reload_model()

    def reload_model(self) -> None:
        try:
            model_path = os.path.join(settings.MODELS_DIR, "naira_logreg.json")
            self.engine.load_model(model_path)
        except Exception:
            pass

    def get_alerts(self, limit: int = 200) -> List[Dict[str, Any]]:
        return list(self._alerts[-int(limit):])

    def _push_alert(self, alert: Dict[str, Any]) -> None:
        metrics_singleton.rolling["alerts_10m"].add()
        self._alerts.append(alert)
        if len(self._alerts) > int(settings.ALERTS_MAX):
            self._alerts = self._alerts[-int(settings.ALERTS_MAX):]
        try:
            os.makedirs(os.path.dirname(self.events_path), exist_ok=True)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            notifier_singleton.notify("alert", alert)
        except Exception:
            metrics_singleton.rolling["errors_10m"].add()

    def scan_once(self) -> List[Dict[str, Any]]:
        metrics_singleton.rolling["scans_10m"].add()
        symbols = self.watchlist.load()
        if not symbols:
            um = UniverseManager(data_dir=settings.DATA_DIR)
            bal = float(settings.BALANCE_USDT)
            out_items = []
            for a in ("crypto", "fx", "metals"):
                tr = tranche_for_balance(a, bal)  # type: ignore[arg-type]
                out_items.extend(um.symbols(a, tr))  # type: ignore[arg-type]
            seen = set()
            symbols = []
            for s in out_items:
                if s not in seen:
                    seen.add(s)
                    symbols.append(s)
        symbols = symbols[: int(settings.MAX_SCAN_SYMBOLS)]
        if not symbols:
            return []
        out = []
        prev = self.status.last_top or []
        prev_syms = {str(x.get("symbol") or "") for x in prev if str(x.get("symbol") or "")}
        t0 = time.time()
        err = None
        try:
            for sym in symbols:
                try:
                    kind = str(classify_symbol(sym)).lower()
                    if kind not in ("crypto", "fx", "metals"):
                        kind = "crypto"
                    tranche = tranche_for_balance(kind, float(settings.BALANCE_USDT))  # type: ignore[arg-type]
                    r, meta = run_multi_brain(
                        engine=self.engine,
                        symbol=sym,
                        provider=settings.SCAN_PROVIDER,
                        base_timeframe=settings.SCAN_BASE_TIMEFRAME,
                        tranche=tranche,
                        include_debug=False,
                    )
                    r["brain"] = meta.final.brain
                    r["regime"] = meta.regime
                    out.append(r)
                except Exception as e:
                    err = str(e)
                    continue
        finally:
            self.status.last_run_ts = int(time.time())
            self.status.last_duration_ms = int((time.time() - t0) * 1000)
            self.status.last_error = err
        bonus = 3.0
        out.sort(key=lambda x: float(x.get("opportunity_score") or 0.0) + (bonus if str(x.get("symbol") or "") in prev_syms else 0.0), reverse=True)
        self.status.last_top = out[:10]
        self._detect_regime_changes(out)
        return out

    def _detect_regime_changes(self, results: List[Dict[str, Any]]) -> None:
        now = datetime.utcnow().isoformat()
        for r in results:
            sym = str(r.get("symbol") or "")
            if not sym:
                continue
            d = str(r.get("direction") or "neutral")
            c = float(r.get("confidence") or 0.0)
            s = float(r.get("opportunity_score") or 0.0)
            prev_d = self._last_dir.get(sym)
            prev_s = float(self._last_score.get(sym, 0.0))
            self._last_dir[sym] = d
            self._last_score[sym] = s
            if prev_d is None:
                continue
            if d != prev_d and c >= 0.65:
                self._push_alert(
                    {
                        "ts": now,
                        "type": "regime_change",
                        "symbol": sym,
                        "from": prev_d,
                        "to": d,
                        "confidence": c,
                        "score": s,
                        "prev_score": prev_s,
                    }
                )
            elif d != "neutral" and prev_d == d and (s - prev_s) >= 20.0 and c >= 0.7:
                self._push_alert(
                    {
                        "ts": now,
                        "type": "opportunity_jump",
                        "symbol": sym,
                        "direction": d,
                        "confidence": c,
                        "score": s,
                        "prev_score": prev_s,
                    }
                )


scanner_singleton = ScannerService()
