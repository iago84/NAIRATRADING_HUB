import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.engine.naira_engine import NairaEngine

from scripts.pipeline_lib.log import info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="Lista separada por comas")
    ap.add_argument("--base_timeframe", default="1h")
    ap.add_argument("--provider", default="csv")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    engine = NairaEngine(data_dir=settings.DATA_DIR)
    items = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    out = []
    info(f"scan_job start provider={args.provider} tf={args.base_timeframe} symbols={len(items)} top={args.top}")
    for sym in items[: int(settings.MAX_SCAN_SYMBOLS)]:
        try:
            out.append(engine.analyze(symbol=sym, provider=args.provider, base_timeframe=args.base_timeframe))
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
    print(json.dumps(out[: int(args.top)], ensure_ascii=False, indent=2))
    info(f"scan_job done items={len(out)}")


if __name__ == "__main__":
    main()
