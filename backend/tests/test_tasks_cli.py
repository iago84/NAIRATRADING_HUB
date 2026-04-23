from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.tasks import build_parser


def test_tasks_parser_all_binance_defaults():
    p = build_parser()
    ns = p.parse_args(["all", "--provider", "binance"])
    assert ns.cmd == "all"
    assert ns.provider == "binance"
    assert ns.entry_mode == "hybrid"
    assert ns.risk_stop_policy == "stop_immediate"


def test_tasks_parser_all_binance_overrides():
    p = build_parser()
    ns = p.parse_args(
        [
            "all",
            "--provider",
            "binance",
            "--entry-mode",
            "pullback",
            "--workers",
            "16",
            "--update-workers",
            "3",
            "--max-equity-drawdown-pct",
            "40",
            "--free-cash-min-pct",
            "0.30",
            "--risk-stop-policy",
            "stop_after_close",
        ]
    )
    assert ns.cmd == "all"
    assert ns.provider == "binance"
    assert ns.entry_mode == "pullback"
    assert ns.workers == 16
    assert ns.update_workers == 3
    assert ns.max_equity_drawdown_pct == 40
    assert ns.free_cash_min_pct == 0.30
    assert ns.risk_stop_policy == "stop_after_close"


def test_parser_backtest_portfolio():
    p = build_parser()
    ns = p.parse_args(["backtest:portfolio", "--provider", "csv"])
    assert ns.cmd == "backtest:portfolio"
