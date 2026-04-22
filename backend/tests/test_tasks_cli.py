from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.tasks import build_parser


def test_tasks_parser_all_binance():
    p = build_parser()
    ns = p.parse_args(["all", "--provider", "binance"])
    assert ns.cmd == "all"
    assert ns.provider == "binance"

