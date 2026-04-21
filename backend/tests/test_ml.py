import unittest
from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine
from app.engine.naira_engine import NairaConfig
from app.engine.dataset import build_trade_dataset, FEATURES
from app.engine.model import train_logreg_sgd, load_model


class TestML(unittest.TestCase):
    def test_dataset_and_model(self):
        eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(entry_mode="none"))
        ds_path = os.path.join(settings.DATASETS_DIR, "unit_TEST.csv")
        r = build_trade_dataset(eng, symbol="TEST", provider="csv", base_timeframe="1h", out_path=ds_path)
        self.assertTrue(os.path.exists(r.path))
        self.assertGreaterEqual(r.rows, 1)
        model_path = os.path.join(settings.MODELS_DIR, "unit_model.json")
        tr = train_logreg_sgd(dataset_csv=r.path, feature_names=FEATURES, out_path=model_path, epochs=50, seed=1)
        self.assertTrue(os.path.exists(tr.path))
        m = load_model(tr.path)
        self.assertIsNotNone(m)
        p = m.predict_proba({k: 0.0 for k in FEATURES})
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)


if __name__ == "__main__":
    unittest.main()
