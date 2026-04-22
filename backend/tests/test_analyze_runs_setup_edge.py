import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.analyze_runs import load_dataset_csv, load_backtest_json, normalize_trade_rows, aggregate_by_setup


def test_setup_edge_multi_sources():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ds1 = base / "a.csv"
        ds1.write_text("setup_primary,pnl,trend_age_bars,ema_compression\nbreakout,10,1,1.0\nbreakout,-5,2,1.2\n", encoding="utf-8")
        ds2 = base / "b.csv"
        ds2.write_text("setup_primary,pnl,trend_age_bars,ema_compression\npullback_ema,3,1,1.0\n", encoding="utf-8")
        bt = base / "bt.json"
        bt.write_text(
            json.dumps(
                {
                    "trades": [
                        {
                            "pnl": 2.0,
                            "setup_primary": "breakout",
                            "entry_meta": {"risk_r": 1.0},
                            "_features": {"trend_age_bars": 1, "ema_compression": 1.0},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rows = []
        rows += load_dataset_csv(str(ds1))
        rows += load_dataset_csv(str(ds2))
        rows += load_backtest_json(str(bt))
        norm = normalize_trade_rows(rows)
        agg = aggregate_by_setup(norm)
        assert "breakout" in agg
        assert agg["breakout"]["n_trades"] == 3

