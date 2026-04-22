from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from scripts.pipeline_lib.docs_gen import render_html, write_html
from scripts.pipeline_lib.paths import PipelinePaths


def cmd_env(args: argparse.Namespace) -> int:
    pp = PipelinePaths(repo_root=REPO_ROOT, data_dir=str(args.data_dir))
    print(pp.data_dir)
    print(pp.history_dir)
    print(pp.reports_dir)
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    pp = PipelinePaths(repo_root=REPO_ROOT, data_dir=str(args.data_dir))
    sections = [
        {"h": "Comandos", "p": "<pre>python scripts/naira_pipeline.py env</pre>"},
    ]
    html = render_html("NAIRA Pipeline", sections)
    write_html(os.path.join(pp.docs_generated_dir, "pipeline.html"), html)
    write_html(os.path.join(pp.docs_generated_dir, "pipeline.pdf.html"), html)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    from app.engine.history_store import HistoryStore
    from app.engine.providers.binance_rest_provider import BinanceRestOHLCVProvider
    from app.engine.providers.mt5_provider import MT5OHLCVProvider
    import pandas as pd
    from datetime import datetime, timedelta

    def normalize_timeframe(tf: str) -> str:
        s = str(tf).strip()
        if s.replace(".", "", 1).isdigit():
            return f"{int(float(s))}d"
        return s

    provider = str(args.provider).strip().lower()
    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    tfs = [normalize_timeframe(t) for t in str(args.timeframes).split(",") if str(t).strip()]
    years = max(1, int(args.years))
    limit = max(1, int(args.limit))
    store = HistoryStore(base_dir=str(args.data_dir))
    out = []
    if provider == "binance":
        ex = BinanceRestOHLCVProvider()
        end = datetime.utcnow()
        start = end - timedelta(days=365 * years)
        for sym in symbols:
            for tf in tfs:
                since = int(start.timestamp() * 1000)
                chunks = []
                for _ in range(5000):
                    df = ex.get_ohlc(symbol=sym, timeframe=tf, limit=limit, since_ms=since)
                    if df is None or df.empty:
                        break
                    chunks.append(df)
                    last_dt = pd.to_datetime(df["datetime"].iloc[-1])
                    since_next = int(last_dt.timestamp() * 1000) + 1
                    if since_next <= since:
                        break
                    since = since_next
                    if last_dt >= end:
                        break
                    if len(df) < limit:
                        break
                df_all = pd.concat(chunks).drop_duplicates(subset=["datetime"]).sort_values("datetime") if chunks else pd.DataFrame()
                if df_all.empty:
                    continue
                path = store.upsert(provider="binance", symbol=sym, timeframe=tf, df=df_all)
                out.append({"symbol": sym, "timeframe": tf, "path": path})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if provider == "mt5":
        mt5 = MT5OHLCVProvider()
        end = datetime.utcnow()
        start = end - timedelta(days=365 * years)
        for sym in symbols:
            for tf in tfs:
                df = mt5.get_ohlc_range(symbol=sym, timeframe=tf, start_ts=int(start.timestamp()), end_ts=int(end.timestamp()))
                if df is None or df.empty:
                    continue
                path = store.upsert(provider="mt5", symbol=sym, timeframe=tf, df=df)
                out.append({"symbol": sym, "timeframe": tf, "path": path})
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("provider inválido (binance|mt5)")


def cmd_scan(args: argparse.Namespace) -> int:
    from app.core.config import settings
    from app.engine.naira_engine import NairaEngine
    from app.engine.multi_brain import run_multi_brain
    from app.engine.filters import classify_symbol
    from app.engine.universe import tranche_for_balance

    provider = str(args.provider).strip()
    base_timeframe = str(args.base_timeframe).strip()
    mode = str(args.mode).strip().lower()
    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    eng = NairaEngine(data_dir=str(args.data_dir))
    out = []
    for sym in symbols[: int(settings.MAX_SCAN_SYMBOLS)]:
        try:
            if mode == "multi":
                kind = str(classify_symbol(sym)).lower()
                bal = float(getattr(args, "balance_usdt", 0.0) or 0.0)
                tr = tranche_for_balance(kind if kind in ("crypto", "fx", "metals") else "crypto", bal)  # type: ignore[arg-type]
                r, _ = run_multi_brain(engine=eng, symbol=sym, provider=provider, base_timeframe=base_timeframe, tranche=tr, include_debug=bool(getattr(args, "include_debug", False)))
                out.append(r)
            else:
                out.append(eng.analyze(symbol=sym, provider=provider, base_timeframe=base_timeframe, include_debug=bool(getattr(args, "include_debug", False))))
        except Exception:
            continue
    out.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="naira_pipeline")
    p.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "backend", "data"))
    p.add_argument("--timing-mode", default="")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp_env = sp.add_parser("env")
    sp_env.set_defaults(fn=cmd_env)
    sp_docs = sp.add_parser("docs")
    sp_docs.set_defaults(fn=cmd_docs)
    sp_dl = sp.add_parser("download")
    sp_dl.add_argument("--provider", required=True)
    sp_dl.add_argument("--symbols", required=True)
    sp_dl.add_argument("--timeframes", required=True)
    sp_dl.add_argument("--years", required=True, type=int)
    sp_dl.add_argument("--limit", default=1000, type=int)
    sp_dl.set_defaults(fn=cmd_download)
    sp_scan = sp.add_parser("scan")
    sp_scan.add_argument("--provider", required=True)
    sp_scan.add_argument("--base-timeframe", required=True)
    sp_scan.add_argument("--symbols", required=True)
    sp_scan.add_argument("--mode", required=True)
    sp_scan.add_argument("--balance-usdt", default=0.0, type=float)
    sp_scan.add_argument("--include-debug", default=False, action="store_true")
    sp_scan.set_defaults(fn=cmd_scan)
    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if str(getattr(args, "timing_mode", "")).strip():
        try:
            from app.core.config import settings

            object.__setattr__(settings, "TIMING_MODE", str(args.timing_mode).strip().lower())
        except Exception:
            pass
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
