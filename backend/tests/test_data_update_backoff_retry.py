from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.tasks import _retry_get_ohlc


def test_backoff_retry_policy_is_applied(monkeypatch):
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("rate limit")
        return []

    monkeypatch.setattr(time, "sleep", lambda *_: None)
    out = _retry_get_ohlc(max_retries=3, backoff_ms=10, min_sleep_ms=0, fn=fn)
    assert calls["n"] == 3
    assert out == []
