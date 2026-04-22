import time
from dataclasses import dataclass
from typing import Dict, Tuple


_mem: Dict[Tuple[str, int], int] = {}


@dataclass(frozen=True)
class RateLimitPolicy:
    per_minute: int = 60


class RateLimiter:
    def __init__(self, policy: RateLimitPolicy | None = None):
        self.policy = policy or RateLimitPolicy()

    def allow(self, key: str) -> bool:
        now = int(time.time())
        minute = now // 60
        k = (str(key), minute)
        n = _mem.get(k, 0) + 1
        _mem[k] = n
        return n <= int(self.policy.per_minute)
