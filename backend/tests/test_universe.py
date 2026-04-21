import unittest
from pathlib import Path
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.universe import UniverseManager, tranche_for_balance


class TestUniverse(unittest.TestCase):
    def test_tranche_crypto(self):
        self.assertEqual(tranche_for_balance("crypto", 0), "T0")
        self.assertEqual(tranche_for_balance("crypto", 199), "T0")
        self.assertEqual(tranche_for_balance("crypto", 200), "T1")
        self.assertEqual(tranche_for_balance("crypto", 999), "T1")
        self.assertEqual(tranche_for_balance("crypto", 1000), "T2")
        self.assertEqual(tranche_for_balance("crypto", 4999), "T2")
        self.assertEqual(tranche_for_balance("crypto", 5000), "T3")

    def test_universe_load(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            wl = base / "watchlists"
            wl.mkdir(parents=True, exist_ok=True)
            (wl / "crypto_top2.json").write_text(json.dumps(["BTCUSDT", "ETHUSDT"]), encoding="utf-8")
            um = UniverseManager(data_dir=str(base))
            self.assertEqual(um.symbols("crypto", "T0"), ["BTCUSDT", "ETHUSDT"])


if __name__ == "__main__":
    unittest.main()
