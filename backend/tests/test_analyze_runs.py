import tempfile
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.analyze_runs import build_markdown_report, load_scan_json, load_random_jsonl


def test_analyze_runs_generates_markdown():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        scan_p = base / "scan.json"
        scan_p.write_text(json.dumps([{"symbol": "X", "direction": "buy", "opportunity_score": 80.0, "entry_kind": "break_retest"}]), encoding="utf-8")
        rnd_p = base / "rnd.jsonl"
        rnd_p.write_text(json.dumps({"run": 0, "symbol": "X", "metrics": {"trades": 10, "total_pnl": 5.0}}) + "\n", encoding="utf-8")
        scan = load_scan_json(str(scan_p))
        rnd = load_random_jsonl(str(rnd_p))
        md = build_markdown_report(scan, rnd)
        assert "scan" in md.lower()
        assert "random" in md.lower()
        out_md = base / "report.md"
        out_md.write_text(md, encoding="utf-8")
        assert out_md.exists()

