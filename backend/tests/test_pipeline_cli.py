import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from scripts.pipeline_lib.manifest import sha256_file, write_manifest, Manifest, now_iso
from scripts.naira_pipeline import build_parser


def test_manifest_write_and_hash():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text("hello", encoding="utf-8")
        h = sha256_file(str(p))
        assert len(h) == 64
        m = Manifest(job_id="x", command="test", args={}, inputs=[], outputs=[], created_at=now_iso())
        out = Path(td) / "manifest.json"
        write_manifest(str(out), m)
        assert out.exists()


def test_parser_env():
    p = build_parser()
    ns = p.parse_args(["env"])
    assert ns.cmd == "env"


def test_parser_download():
    p = build_parser()
    ns = p.parse_args(["download", "--provider", "binance", "--symbols", "BTCUSDT", "--timeframes", "1h", "--years", "1"])
    assert ns.cmd == "download"


def test_parser_scan():
    p = build_parser()
    ns = p.parse_args(["scan", "--provider", "csv", "--base-timeframe", "1h", "--symbols", "TEST", "--mode", "multi"])
    assert ns.cmd == "scan"
