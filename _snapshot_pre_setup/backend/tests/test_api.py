import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app


class TestAPI(unittest.TestCase):
    def test_health_and_signal(self):
        c = TestClient(app)
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        r = c.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        r = c.get("/api/v1/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("rolling", r.json())
        r = c.get("/api/v1/naira/signal", params={"symbol": "TEST", "provider": "csv", "base_timeframe": "1h"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json().get("direction"), ("buy", "sell", "neutral"))
        r = c.get("/api/v1/naira/signal", params={"symbol": "TEST", "provider": "csv", "base_timeframe": "1h", "mode": "multi"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json().get("direction"), ("buy", "sell", "neutral"))

    def test_portfolio_backtest_requires_trader(self):
        c = TestClient(app)
        r = c.post("/api/v1/naira/portfolio/backtest", json={"symbols": ["TEST"], "provider": "csv", "base_timeframe": "1h"})
        self.assertIn(r.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
