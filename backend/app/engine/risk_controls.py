from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RiskLimits:
    kill_switch: bool = False
    max_notifies_per_day: int = 300
    max_signals_per_day: int = 600
    cooldown_minutes: int = 0


@dataclass
class RiskState:
    day: int = 0
    notifies: int = 0
    signals: int = 0
    last_block_ts: int = 0


class RiskStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> RiskLimits:
        if not os.path.exists(self.path):
            return RiskLimits()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.loads(f.read())
            return RiskLimits(**payload)
        except Exception:
            return RiskLimits()

    def save(self, limits: RiskLimits) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps(asdict(limits), ensure_ascii=False, indent=2))


class RiskManager:
    def __init__(self, store: RiskStore):
        self.store = store
        self.state_by_key: Dict[str, RiskState] = {}

    def _today(self) -> int:
        return int(time.time() // 86400)

    def _state(self, key: str) -> RiskState:
        k = str(key or "anon")
        st = self.state_by_key.get(k)
        if st is None:
            st = RiskState(day=self._today())
            self.state_by_key[k] = st
        if st.day != self._today():
            st.day = self._today()
            st.notifies = 0
            st.signals = 0
            st.last_block_ts = 0
        return st

    def allow_signal(self, key: str) -> tuple[bool, str]:
        lim = self.store.load()
        if lim.kill_switch:
            return False, "kill_switch"
        st = self._state(key)
        if lim.cooldown_minutes > 0 and st.last_block_ts:
            if (int(time.time()) - int(st.last_block_ts)) < int(lim.cooldown_minutes) * 60:
                return False, "cooldown"
        if st.signals >= int(lim.max_signals_per_day):
            st.last_block_ts = int(time.time())
            return False, "max_signals_per_day"
        st.signals += 1
        return True, "ok"

    def allow_notify(self, key: str) -> tuple[bool, str]:
        lim = self.store.load()
        if lim.kill_switch:
            return False, "kill_switch"
        st = self._state(key)
        if lim.cooldown_minutes > 0 and st.last_block_ts:
            if (int(time.time()) - int(st.last_block_ts)) < int(lim.cooldown_minutes) * 60:
                return False, "cooldown"
        if st.notifies >= int(lim.max_notifies_per_day):
            st.last_block_ts = int(time.time())
            return False, "max_notifies_per_day"
        st.notifies += 1
        return True, "ok"

    def status(self, key: str) -> Dict[str, Any]:
        lim = self.store.load()
        st = self._state(key)
        return {"limits": asdict(lim), "state": asdict(st)}
