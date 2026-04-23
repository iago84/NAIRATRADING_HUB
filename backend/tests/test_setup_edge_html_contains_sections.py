import json
import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.analyze_runs import main as analyze_main


def test_setup_edge_html_contains_sections(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ds_dir = base / "datasets"
        ds_dir.mkdir(parents=True, exist_ok=True)
        (ds_dir / "x_ml.csv").write_text("setup_primary,pnl,win\nbreakout,1,1\nbreakout,-0.5,0\n", encoding="utf-8")
        bt = base / "backtest_1h_XRPUSDT.json"
        bt.write_text(
            json.dumps(
                {
                    "metrics": {"trades": 2, "total_pnl": 0.5, "gates_timing_blocked": 3},
                    "late_entry_report": {"recommendations": ["relax_age", "relax_compression"]},
                    "trades": [{"pnl": 0.5, "setup_primary": "breakout", "entry_meta": {"risk_r": 1.0}}],
                }
            ),
            encoding="utf-8",
        )
        out_html = os.path.join(td, "setup_edge.html")
        out_md = os.path.join(td, "setup_edge.md")
        out_json = os.path.join(td, "setup_edge.json")
        argv = [
            "analyze_runs.py",
            "--dataset-dir",
            str(ds_dir),
            "--backtest-json",
            str(bt),
            "--out-html",
            out_html,
            "--out-md",
            out_md,
            "--out-json",
            out_json,
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = analyze_main()
        assert rc == 0
        html = Path(out_html).read_text(encoding="utf-8")
        assert "Datasets" in html
        assert "Backtests" in html
        assert "Timing gate" in html
