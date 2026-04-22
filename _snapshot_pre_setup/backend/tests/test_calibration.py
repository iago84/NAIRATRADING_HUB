import unittest
from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.engine.calibration import calibration_report
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.dataset import build_trade_dataset, FEATURES
from app.engine.model import train_logreg_sgd


class TestCalibration(unittest.TestCase):
    def test_calibration_report(self):
        eng = NairaEngine(data_dir=settings.DATA_DIR, config=NairaConfig(entry_mode="none"))
        ds_path = os.path.join(settings.DATASETS_DIR, "cal_TEST.csv")
        ds = build_trade_dataset(eng, symbol="TEST", provider="csv", base_timeframe="1h", out_path=ds_path)
        self.assertGreaterEqual(ds.rows, 1)
        model_path = os.path.join(settings.MODELS_DIR, "cal_model.json")
        train_logreg_sgd(dataset_csv=ds.path, feature_names=FEATURES, out_path=model_path, epochs=30, seed=1)
        rep = calibration_report(dataset_csv=ds.path, model_path=model_path, bins=5)
        self.assertIn("ece", rep)
        self.assertIn("brier", rep)
        self.assertIn("bins", rep)


if __name__ == "__main__":
    unittest.main()
