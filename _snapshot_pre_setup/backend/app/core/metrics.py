from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


@dataclass
class RollingCounter:
    window_seconds: int
    events: Deque[float]

    def add(self, ts: Optional[float] = None) -> None:
        now = float(ts if ts is not None else time.time())
        self.events.append(now)
        self._trim(now)

    def count(self, now: Optional[float] = None) -> int:
        n = float(now if now is not None else time.time())
        self._trim(n)
        return int(len(self.events))

    def _trim(self, now: float) -> None:
        cutoff = float(now) - float(self.window_seconds)
        while self.events and float(self.events[0]) < cutoff:
            self.events.popleft()


class Metrics:
    def __init__(self):
        self.started_ts = int(time.time())
        self.counters: Dict[str, int] = {}
        self.rolling: Dict[str, RollingCounter] = {
            "requests_1m": RollingCounter(window_seconds=60, events=deque()),
            "requests_10m": RollingCounter(window_seconds=600, events=deque()),
            "signals_10m": RollingCounter(window_seconds=600, events=deque()),
            "scans_10m": RollingCounter(window_seconds=600, events=deque()),
            "alerts_10m": RollingCounter(window_seconds=600, events=deque()),
            "notify_10m": RollingCounter(window_seconds=600, events=deque()),
            "errors_10m": RollingCounter(window_seconds=600, events=deque()),
        }
        self.latency_ms_10m: Deque[float] = deque()
        self.latency_window_seconds = 600

    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + int(n)

    def add_latency(self, ms: float) -> None:
        now = time.time()
        self.latency_ms_10m.append((now, float(ms)))
        cutoff = now - float(self.latency_window_seconds)
        while self.latency_ms_10m and float(self.latency_ms_10m[0][0]) < cutoff:
            self.latency_ms_10m.popleft()

    def summary(self) -> dict:
        now = time.time()
        lat = [float(x[1]) for x in self.latency_ms_10m]
        p50 = float(sorted(lat)[int(0.5 * (len(lat) - 1))]) if lat else 0.0
        p95 = float(sorted(lat)[int(0.95 * (len(lat) - 1))]) if lat else 0.0
        return {
            "started_ts": self.started_ts,
            "counters": dict(self.counters),
            "rolling": {k: v.count(now) for k, v in self.rolling.items()},
            "latency_ms_10m": {"p50": p50, "p95": p95, "count": len(lat)},
        }


metrics_singleton = Metrics()
