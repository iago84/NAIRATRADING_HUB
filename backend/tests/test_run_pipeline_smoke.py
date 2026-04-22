import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.run_pipeline import pick_top_symbols


def test_pick_top_symbols_top10():
    items = [{"symbol": f"S{i}", "opportunity_score": float(i)} for i in range(30)]
    out = pick_top_symbols(items, top_n=10)
    assert len(out) == 10
    assert out[0] == "S29"

