from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.core.config import settings
from app.engine.calibration import calibration_report
from app.engine.dataset import build_trade_dataset
from app.engine.history_store import HistoryStore
from app.engine.model import train_logreg_sgd_multi
from app.engine.naira_engine import NairaEngine, NairaConfig
from app.engine.multi_brain import run_multi_brain
from app.engine.providers.binance_rest_provider import BinanceRestOHLCVProvider


RUN_TFS = ["5m", "15m", "30m", "1h"]
HT_TFS = ["4h", "1d", "1w"]
DEFAULT_TFS = list(RUN_TFS)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_hms() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")


def _ensure_dir(p: str) -> str:
    os.makedirs(p, exist_ok=True)
    return p


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read() or "")
    except Exception:
        return default


def _write_json(path: str, obj: Any) -> None:
    _ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


def _universe_size() -> int:
    try:
        v = int(os.getenv("PIPELINE_UNIVERSE", "30").strip() or "30")
        return 100 if v >= 100 else 30
    except Exception:
        return 30


def _top_n() -> int:
    try:
        v = int(os.getenv("PIPELINE_TOPN", "10").strip() or "10")
        return max(1, min(100, v))
    except Exception:
        return 10


def _watchlist_path(provider: str) -> str:
    p = str(provider).lower()
    if p == "binance":
        wl = "crypto_top100.json" if _universe_size() >= 100 else "crypto_top30.json"
        return os.path.join(str(settings.DATA_DIR), "watchlists", wl)
    if p == "mt5":
        return os.path.join(str(settings.DATA_DIR), "watchlists", "fx_majors_minors.json")
    return os.path.join(str(settings.DATA_DIR), "watchlists", "default.json")


def load_symbols(provider: str) -> List[str]:
    wl = _watchlist_path(provider)
    obj = _read_json(wl, {})
    items = obj.get("symbols") if isinstance(obj, dict) else obj
    out = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not out and str(provider).lower() == "csv":
        wl2 = os.path.join(str(settings.DATA_DIR), "watchlists", "crypto_top30.json")
        obj2 = _read_json(wl2, {})
        it2 = obj2.get("symbols") if isinstance(obj2, dict) else obj2
        out = [str(x).strip() for x in (it2 or []) if str(x).strip()]
    return out[: _universe_size()]


def pick_top_symbols(scan_items: List[Dict[str, Any]], top_n: int) -> List[str]:
    items = list(scan_items or [])
    items.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
    out = []
    for it in items:
        s = str(it.get("symbol") or "").strip()
        if not s:
            continue
        out.append(s)
        if len(out) >= int(top_n):
            break
    return out


def make_run_dir(provider: str) -> str:
    base = os.path.join(str(settings.DATA_DIR), "reports", _utc_day(), f"run_{_utc_hms()}_{str(provider).lower()}")
    return _ensure_dir(base)


def _timeframe_window_days(tf: str) -> int:
    t = str(tf)
    if t == "5m":
        return 14
    if t == "15m":
        return 45
    if t == "30m":
        return 90
    if t == "1h":
        return 180
    if t == "4h":
        return 365
    if t == "1d":
        return 365 * 3
    if t == "1w":
        return 365 * 7
    return 365


def cmd_data_update(
    provider: str,
    run_dir: str,
    symbols: List[str],
    tfs: List[str],
    update_workers: int,
    update_min_sleep_ms: int,
    update_backoff_ms: int,
    update_max_retries: int,
) -> Dict[str, Any]:
    p = str(provider).lower()
    store = HistoryStore(base_dir=str(settings.DATA_DIR))
    updated = 0
    errors: List[str] = []
    if p in ("binance", "csv"):
        ex = BinanceRestOHLCVProvider()
        min_sleep_s = float(max(0, int(update_min_sleep_ms))) / 1000.0
        backoff_s = float(max(0, int(update_backoff_ms))) / 1000.0
        max_retries = int(max(0, int(update_max_retries)))
        def _update_one(sym: str, tf: str) -> tuple[bool, Optional[str]]:
            try:
                latest = store.latest_datetime(provider="csv", symbol=sym, timeframe=tf)
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=_timeframe_window_days(tf))
                since_ms = int(start.timestamp() * 1000)
                if latest is not None:
                    try:
                        since_ms = int(pd.to_datetime(latest).timestamp() * 1000) - 1
                    except Exception:
                        since_ms = since_ms
                chunks = []
                cur = int(since_ms)
                for _ in range(50):
                    df = None
                    last_err: Optional[BaseException] = None
                    for attempt in range(int(max_retries) + 1):
                        try:
                            if min_sleep_s > 0:
                                time.sleep(float(min_sleep_s))
                            df = ex.get_ohlc(symbol=sym, timeframe=tf, limit=1000, since_ms=cur)
                            last_err = None
                            break
                        except BaseException as e:
                            last_err = e
                            if attempt >= int(max_retries):
                                break
                            if backoff_s > 0:
                                time.sleep(float(backoff_s) * float(attempt + 1))
                    if last_err is not None and df is None:
                        raise last_err
                    if df is None or df.empty:
                        break
                    chunks.append(df)
                    last_dt = pd.to_datetime(df["datetime"].iloc[-1])
                    nxt = int(last_dt.timestamp() * 1000) + 1
                    if nxt <= cur:
                        break
                    cur = nxt
                    if len(df) < 1000:
                        break
                if not chunks:
                    return (False, None)
                df_all = pd.concat(chunks).drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
                try:
                    store.upsert(provider="binance", symbol=sym, timeframe=tf, df=df_all)
                except Exception:
                    pass
                store.upsert(provider="csv", symbol=sym, timeframe=tf, df=df_all)
                return (True, None)
            except Exception as e:
                return (False, f"{sym}:{tf}:{type(e).__name__}")

        w = int(max(1, int(update_workers)))
        if w <= 1:
            for sym in symbols:
                for tf in tfs:
                    ok, err = _update_one(sym, tf)
                    if ok:
                        updated += 1
                    if err:
                        errors.append(err)
        else:
            with ThreadPoolExecutor(max_workers=w) as pool:
                futs = [pool.submit(_update_one, sym, tf) for sym in symbols for tf in tfs]
                for f in as_completed(futs):
                    ok, err = f.result()
                    if ok:
                        updated += 1
                    if err:
                        errors.append(err)
    elif p == "mt5":
        try:
            from app.engine.providers.mt5_provider import MT5OHLCVProvider

            mt5 = MT5OHLCVProvider()
            for sym in symbols:
                for tf in tfs:
                    try:
                        df = mt5.get_ohlc(symbol=sym, timeframe=tf, bars=5000)
                        if df is None or df.empty:
                            continue
                        try:
                            store.upsert(provider="mt5", symbol=sym, timeframe=tf, df=df)
                        except Exception:
                            pass
                        store.upsert(provider="csv", symbol=sym, timeframe=tf, df=df)
                        updated += 1
                    except Exception as e:
                        errors.append(f"{sym}:{tf}:{type(e).__name__}")
                        continue
        except Exception:
            errors.append("mt5_provider_unavailable")
    payload = {"provider": p, "updated": int(updated), "errors": errors, "tfs": list(tfs), "symbols": int(len(symbols))}
    _write_json(os.path.join(run_dir, "data_update.json"), payload)
    try:
        print(f"data:update provider={p} updated={int(updated)} errors={len(errors)}")
    except Exception:
        pass
    return payload


def cmd_scan(provider: str, run_dir: str, symbols: List[str], tfs: List[str], entry_mode: str, workers: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tf in tfs:
        rows = []
        loc = threading.local()

        def _scan_one(sym: str) -> Optional[Dict[str, Any]]:
            try:
                eng = getattr(loc, "eng", None)
                if eng is None:
                    eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                    setattr(loc, "eng", eng)
                r, _ = run_multi_brain(engine=eng, symbol=sym, provider=str(provider), base_timeframe=tf, tranche="T1", include_debug=False)
                return r
            except Exception:
                return None

        items = symbols[: int(settings.MAX_SCAN_SYMBOLS)]
        w = int(max(1, int(workers)))
        if w <= 1:
            for sym in items:
                r = _scan_one(sym)
                if r:
                    rows.append(r)
        else:
            with ThreadPoolExecutor(max_workers=w) as pool:
                futs = [pool.submit(_scan_one, sym) for sym in items]
                for f in as_completed(futs):
                    r = f.result()
                    if r:
                        rows.append(r)
        rows.sort(key=lambda x: float(x.get("opportunity_score") or 0.0), reverse=True)
        p = os.path.join(run_dir, f"scan_{tf}.json")
        _write_json(p, rows)
        out[tf] = p
        try:
            print(f"scan tf={tf} items={len(rows)}")
        except Exception:
            pass
    return out


def cmd_backtest_top(
    provider: str,
    run_dir: str,
    scan_paths: Dict[str, str],
    top_n: int,
    tfs: List[str],
    entry_mode: str,
    workers: int,
    max_equity_drawdown_pct: float,
    free_cash_min_pct: float,
    risk_stop_policy: str,
) -> List[str]:
    out = []
    tasks: List[tuple[str, str]] = []
    for tf in tfs:
        sp = scan_paths.get(tf) or os.path.join(run_dir, f"scan_{tf}.json")
        scan_items = _read_json(sp, [])
        top_syms = pick_top_symbols(list(scan_items or []), top_n=int(top_n))
        for sym in top_syms:
            tasks.append((tf, sym))

    loc = threading.local()

    def _bt_one(tf: str, sym: str) -> Optional[tuple[str, str, Dict[str, Any]]]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            r = eng.backtest(
                symbol=sym,
                provider=str(provider),
                base_timeframe=tf,
                max_bars=5000,
                max_equity_drawdown_pct=float(max_equity_drawdown_pct),
                free_cash_min_pct=float(free_cash_min_pct),
                risk_stop_policy=str(risk_stop_policy),
            )
            return (tf, sym, r)
        except Exception:
            return None

    w = int(max(1, int(workers)))
    try:
        print(f"backtest:top tasks={len(tasks)} workers={w} sizing_mode={sizing_mode}")
    except Exception:
        pass
    if w <= 1:
        for tf, sym in tasks:
            res = _bt_one(tf, sym)
            if not res:
                continue
            tf2, sym2, r = res
            p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
            _write_json(p, r)
            out.append(p)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_bt_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                tf2, sym2, r = res
                p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
                _write_json(p, r)
                out.append(p)
    try:
        print(f"backtest:top done files={len(out)}")
    except Exception:
        pass
    return out


def cmd_backtest_global(
    provider: str,
    run_dir: str,
    symbols: List[str],
    tfs: List[str],
    entry_mode: str,
    workers: int,
    max_equity_drawdown_pct: float,
    free_cash_min_pct: float,
    risk_stop_policy: str,
) -> List[str]:
    out = []
    tasks = [(tf, sym) for tf in tfs for sym in symbols]
    loc = threading.local()

    def _bt_one(tf: str, sym: str) -> Optional[tuple[str, str, Dict[str, Any]]]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            r = eng.backtest(
                symbol=sym,
                provider=str(provider),
                base_timeframe=tf,
                max_bars=5000,
                max_equity_drawdown_pct=float(max_equity_drawdown_pct),
                free_cash_min_pct=float(free_cash_min_pct),
                risk_stop_policy=str(risk_stop_policy),
            )
            return (tf, sym, r)
        except Exception:
            return None

    w = int(max(1, int(workers)))
    try:
        print(f"backtest:global tasks={len(tasks)} workers={w} sizing_mode={sizing_mode}")
    except Exception:
        pass
    if w <= 1:
        for tf, sym in tasks:
            res = _bt_one(tf, sym)
            if not res:
                continue
            tf2, sym2, r = res
            p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
            _write_json(p, r)
            out.append(p)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_bt_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                res = f.result()
                if not res:
                    continue
                tf2, sym2, r = res
                p = os.path.join(run_dir, f"backtest_{tf2}_{sym2}.json")
                _write_json(p, r)
                out.append(p)
    try:
        print(f"backtest:global done files={len(out)}")
    except Exception:
        pass
    return out


def cmd_dataset_build(provider: str, symbols: List[str], tfs: List[str], entry_mode: str, workers: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    tasks = [(tf, sym) for tf in tfs for sym in symbols]
    loc = threading.local()

    def _ds_one(tf: str, sym: str) -> Optional[Dict[str, Any]]:
        try:
            eng = getattr(loc, "eng", None)
            if eng is None:
                eng = NairaEngine(data_dir=str(settings.DATA_DIR), config=NairaConfig(strategy_mode="multi", entry_mode=str(entry_mode)))
                setattr(loc, "eng", eng)
            ds_path = os.path.join(str(settings.DATASETS_DIR), f"{sym}_{str(provider).lower()}_{tf}_ml.csv")
            r = build_trade_dataset(eng, symbol=sym, provider=str(provider), base_timeframe=tf, out_path=ds_path)
            return {"path": str(r.path), "rows": int(r.rows), "symbol": str(sym), "timeframe": str(tf), "provider": str(provider).lower()}
        except Exception:
            return None

    w = int(max(1, int(workers)))
    try:
        print(f"dataset:build tasks={len(tasks)} workers={w}")
    except Exception:
        pass
    if w <= 1:
        for tf, sym in tasks:
            it = _ds_one(tf, sym)
            if it:
                out.append(it)
    else:
        with ThreadPoolExecutor(max_workers=w) as pool:
            futs = [pool.submit(_ds_one, tf, sym) for tf, sym in tasks]
            for f in as_completed(futs):
                it = f.result()
                if it:
                    out.append(it)
    try:
        non_empty = sum(1 for x in out if int(x.get("rows") or 0) > 0)
        print(f"dataset:build done files={len(out)} non_empty={int(non_empty)}")
    except Exception:
        pass
    return out


def cmd_report_setup_edge(run_dir: str, dataset_paths: List[str], backtest_paths: List[str]) -> Dict[str, str]:
    try:
        from scripts.analyze_runs import main as analyze_main

        argv = []
        for p in dataset_paths:
            argv += ["--dataset-csv", str(p)]
        for p in backtest_paths:
            argv += ["--backtest-json", str(p)]
        md = os.path.join(run_dir, "setup_edge.md")
        js = os.path.join(run_dir, "setup_edge.json")
        argv += ["--out-md", md, "--out-json", js]
        sys.argv = ["analyze_runs.py"] + argv
        analyze_main()
        return {"md": md, "json": js}
    except Exception:
        return {}


def _sparkline_svg(values: List[float], width: int = 240, height: int = 48) -> str:
    if not values:
        return ""
    xs = [float(i) for i in range(len(values))]
    ys = [float(v) for v in values]
    y_min = min(ys)
    y_max = max(ys)
    if y_max <= y_min:
        y_max = y_min + 1.0
    x_min = 0.0
    x_max = float(max(1, len(xs) - 1))

    pts = []
    for i, v in enumerate(ys):
        x = (float(i) - x_min) / (x_max - x_min) * float(width)
        y = float(height) - ((float(v) - float(y_min)) / (float(y_max) - float(y_min)) * float(height))
        pts.append(f"{x:.2f},{y:.2f}")
    poly = " ".join(pts)
    return f'<svg width="{int(width)}" height="{int(height)}" viewBox="0 0 {int(width)} {int(height)}" xmlns="http://www.w3.org/2000/svg"><polyline fill="none" stroke="currentColor" stroke-width="1.5" points="{poly}"/></svg>'


def cmd_report_html(run_dir: str, backtest_paths: List[str], datasets: List[Dict[str, Any]]) -> Dict[str, str]:
    rows = []
    for p in list(backtest_paths or []):
        try:
            d = _read_json(str(p), {})
            met = d.get("metrics") or {}
            trades = d.get("trades") or []
            sym = str(d.get("symbol") or "")
            tf = str(d.get("base_timeframe") or "")
            total_pnl = float(met.get("total_pnl") or 0.0)
            pf = float(met.get("profit_factor") or 0.0)
            win = float(met.get("win_rate_pct") or 0.0)
            ntr = int(met.get("trades") or 0)

            ai_vals = []
            ai_w = []
            ai_l = []
            brier = []
            eq = []
            for t in trades:
                pnl = float(t.get("pnl_total") if t.get("pnl_total") is not None else (t.get("pnl") or 0.0))
                y = 1.0 if pnl > 0 else 0.0
                em = t.get("entry_meta") or {}
                ap = em.get("ai_prob_entry")
                if ap is not None:
                    try:
                        apf = float(ap)
                        ai_vals.append(apf)
                        if y > 0:
                            ai_w.append(apf)
                        else:
                            ai_l.append(apf)
                        brier.append((apf - y) ** 2)
                    except Exception:
                        pass
                eq.append((eq[-1] if eq else 10000.0) + float(pnl))

            ai_mean = float(sum(ai_vals) / max(1, len(ai_vals))) if ai_vals else None
            ai_mean_w = float(sum(ai_w) / max(1, len(ai_w))) if ai_w else None
            ai_mean_l = float(sum(ai_l) / max(1, len(ai_l))) if ai_l else None
            ai_sep = (float(ai_mean_w) - float(ai_mean_l)) if (ai_mean_w is not None and ai_mean_l is not None) else None
            brier_mean = float(sum(brier) / max(1, len(brier))) if brier else None

            rows.append(
                {
                    "symbol": sym,
                    "timeframe": tf,
                    "trades": ntr,
                    "total_pnl": total_pnl,
                    "profit_factor": pf,
                    "win_rate_pct": win,
                    "ai_mean": ai_mean,
                    "ai_sep": ai_sep,
                    "ai_brier": brier_mean,
                    "spark": _sparkline_svg(eq),
                    "blocked_timing_gate": int(met.get("blocked_timing_gate") or 0),
                    "blocked_structural_gate": int(met.get("blocked_structural_gate") or 0),
                    "blocked_confluence_gate": int(met.get("blocked_confluence_gate") or 0),
                    "blocked_threshold_gate": int(met.get("blocked_threshold_gate") or 0),
                    "blocked_higher_tf": int(met.get("blocked_higher_tf") or 0),
                }
            )
        except Exception:
            continue

    rows.sort(key=lambda x: float(x.get("total_pnl") or 0.0), reverse=True)
    top = rows[:20]
    bottom = list(reversed(rows[-20:])) if rows else []

    ds_rows = []
    for d in list(datasets or []):
        try:
            ds_rows.append(
                {
                    "symbol": str(d.get("symbol") or ""),
                    "timeframe": str(d.get("timeframe") or ""),
                    "rows": int(d.get("rows") or 0),
                    "path": str(d.get("path") or ""),
                }
            )
        except Exception:
            continue
    ds_rows.sort(key=lambda x: (str(x.get("timeframe")), str(x.get("symbol"))))

    def fmt(x: Any, nd: int = 6) -> str:
        if x is None:
            return ""
        try:
            return f"{float(x):.{int(nd)}f}"
        except Exception:
            return str(x)

    html_rows_top = []
    for r in top:
        html_rows_top.append(
            "<tr>"
            f"<td>{r['symbol']}</td>"
            f"<td>{r['timeframe']}</td>"
            f"<td>{int(r['trades'])}</td>"
            f"<td>{fmt(r['total_pnl'], 6)}</td>"
            f"<td>{fmt(r['profit_factor'], 3)}</td>"
            f"<td>{fmt(r['win_rate_pct'], 2)}</td>"
            f"<td>{fmt(r['ai_mean'], 3)}</td>"
            f"<td>{fmt(r['ai_sep'], 3)}</td>"
            f"<td>{fmt(r['ai_brier'], 3)}</td>"
            f"<td class='spark'>{r['spark']}</td>"
            "</tr>"
        )

    html_rows_bottom = []
    for r in bottom:
        html_rows_bottom.append(
            "<tr>"
            f"<td>{r['symbol']}</td>"
            f"<td>{r['timeframe']}</td>"
            f"<td>{int(r['trades'])}</td>"
            f"<td>{fmt(r['total_pnl'], 6)}</td>"
            f"<td>{fmt(r['profit_factor'], 3)}</td>"
            f"<td>{fmt(r['win_rate_pct'], 2)}</td>"
            f"<td>{fmt(r['ai_mean'], 3)}</td>"
            f"<td>{fmt(r['ai_sep'], 3)}</td>"
            f"<td>{fmt(r['ai_brier'], 3)}</td>"
            f"<td class='spark'>{r['spark']}</td>"
            "</tr>"
        )

    ds_html = []
    for r in ds_rows:
        ds_html.append(
            "<tr>"
            f"<td>{r['symbol']}</td>"
            f"<td>{r['timeframe']}</td>"
            f"<td>{int(r['rows'])}</td>"
            f"<td class='mono'>{r['path']}</td>"
            "</tr>"
        )

    summary = {"n_backtests": int(len(rows)), "n_datasets": int(len(ds_rows))}
    _write_json(os.path.join(run_dir, "report_summary.json"), summary)

    out_html = os.path.join(run_dir, "report.html")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Naira Pipeline Report</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; color: #111; }}
    h1 {{ font-size: 20px; margin: 0 0 12px 0; }}
    h2 {{ font-size: 16px; margin: 20px 0 8px 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: #444; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; }}
    .spark {{ color: #0f766e; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
    .note {{ color: #555; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>Naira Pipeline Report</h1>
  <div class="note mono">{out_html}</div>
  <div class="note">Top/Bottom se calculan por total_pnl del backtest. Las curvas son equity acumulada por trades (pnl_total si existe).</div>

  <h2>Top Mercados</h2>
  <table>
    <thead>
      <tr>
        <th>Symbol</th><th>TF</th><th>Trades</th><th>Total PnL</th><th>PF</th><th>Win%</th><th>AI mean</th><th>AI sep</th><th>Brier</th><th>Equity</th>
      </tr>
    </thead>
    <tbody>
      {''.join(html_rows_top)}
    </tbody>
  </table>

  <h2>Mercados Negativos / No Rentables</h2>
  <div class="note">Diagnóstico rápido: si hay pocos trades, o muchos bloqueos por gates (timing/struct/threshold/confluence), revisar tuning.</div>
  <table>
    <thead>
      <tr>
        <th>Symbol</th><th>TF</th><th>Trades</th><th>Total PnL</th><th>PF</th><th>Win%</th><th>AI mean</th><th>AI sep</th><th>Brier</th><th>Equity</th>
      </tr>
    </thead>
    <tbody>
      {''.join(html_rows_bottom)}
    </tbody>
  </table>

  <h2>Datasets</h2>
  <div class="note">Incluye rows=0 para visibilidad. Entrenamiento usa solo rows &gt; 0.</div>
  <table>
    <thead>
      <tr><th>Symbol</th><th>TF</th><th>Rows</th><th>Path</th></tr>
    </thead>
    <tbody>
      {''.join(ds_html)}
    </tbody>
  </table>
</body>
</html>
"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    return {"html": out_html}


def cmd_train_stack(run_dir: str, dataset_paths: List[str]) -> Dict[str, Any]:
    if not dataset_paths:
        return {"error": "no datasets"}
    out_path = os.path.join(str(settings.MODELS_DIR), "naira_logreg_stack.json")
    feats = []
    try:
        from app.engine.dataset import FEATURES

        feats = list(FEATURES)
    except Exception:
        feats = []
    r = train_logreg_sgd_multi(dataset_csvs=list(dataset_paths), feature_names=feats, out_path=out_path, lr=0.15, epochs=200, l2=0.001, seed=7)
    payload = {"model_path": out_path, "rows": int(r.rows), "accuracy": float(r.accuracy), "feature_names": list(r.feature_names)}
    _write_json(os.path.join(run_dir, "train.json"), payload)
    return payload


def cmd_calibrate(run_dir: str, dataset_paths: List[str]) -> Dict[str, Any]:
    if not dataset_paths:
        return {"error": "no datasets"}
    out_path = os.path.join(str(settings.MODELS_DIR), "naira_logreg_stack.json")
    try:
        import pandas as pd

        dfs = []
        for p in dataset_paths:
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    dfs.append(df)
            except Exception:
                continue
        if not dfs:
            return {"error": "datasets vacíos"}
        df_all = pd.concat(dfs, ignore_index=True)
        tmp = os.path.join(run_dir, "calibration_dataset.csv")
        df_all.to_csv(tmp, index=False)
        rep = calibration_report(dataset_csv=tmp, model_path=out_path, bins=10)
        _write_json(os.path.join(run_dir, "calibration.json"), rep)
        return rep
    except Exception:
        return {"error": "calibration_failed"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tasks")
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in (
        "data:update",
        "scan",
        "backtest:top",
        "backtest:global",
        "dataset:build",
        "report:setup-edge",
        "report:html",
        "pipeline:report",
        "pipeline:train",
        "train:stack",
        "train:calibrate",
        "all",
    ):
        sub = sp.add_parser(name)
        sub.add_argument("--provider", required=True, choices=["binance", "mt5", "csv"])
        sub.add_argument("--entry-mode", default=os.getenv("PIPELINE_ENTRY_MODE", "hybrid"), choices=["hybrid", "pullback", "break_retest", "mean_reversion", "regime"])
        sub.add_argument("--workers", type=int, default=int(os.getenv("PIPELINE_WORKERS", "8") or "8"))
        sub.add_argument("--update-workers", type=int, default=int(os.getenv("PIPELINE_UPDATE_WORKERS", "2") or "2"))
        sub.add_argument("--update-min-sleep-ms", type=int, default=int(os.getenv("PIPELINE_UPDATE_MIN_SLEEP_MS", "0") or "0"))
        sub.add_argument("--update-backoff-ms", type=int, default=int(os.getenv("PIPELINE_UPDATE_BACKOFF_MS", "250") or "250"))
        sub.add_argument("--update-max-retries", type=int, default=int(os.getenv("PIPELINE_UPDATE_MAX_RETRIES", "3") or "3"))
        sub.add_argument("--max-equity-drawdown-pct", type=float, default=float(os.getenv("PIPELINE_MAX_DD_PCT", "50.0") or "50.0"))
        sub.add_argument("--free-cash-min-pct", type=float, default=float(os.getenv("PIPELINE_FREE_CASH_MIN_PCT", "0.20") or "0.20"))
        sub.add_argument(
            "--risk-stop-policy",
            default=os.getenv("PIPELINE_RISK_STOP_POLICY", "stop_immediate"),
            choices=["stop_immediate", "stop_no_new_trades", "stop_after_close"],
        )
        sub.add_argument("--sizing-mode", default=os.getenv("PIPELINE_SIZING_MODE", "ai_risk"), choices=["fixed_qty", "fixed_risk", "ai_risk"])
        sub.add_argument("--risk-per-trade-pct", type=float, default=float(os.getenv("PIPELINE_RISK_PCT", "2.0") or "2.0"))
        sub.add_argument("--ai-risk-min-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MIN_PCT", "1.0") or "1.0"))
        sub.add_argument("--ai-risk-max-pct", type=float, default=float(os.getenv("PIPELINE_AI_RISK_MAX_PCT", "5.0") or "5.0"))
        sub.add_argument("--max-leverage", type=float, default=float(os.getenv("PIPELINE_MAX_LEVERAGE", "1.0") or "1.0"))
    return p


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    provider = str(args.provider).lower()
    run_dir = make_run_dir(provider)
    run_tfs = list(RUN_TFS)
    ht_tfs = list(HT_TFS)
    update_tfs = run_tfs + ht_tfs
    symbols = load_symbols(provider)
    entry_mode = str(args.entry_mode)
    workers = int(args.workers)
    update_workers = int(args.update_workers)
    update_min_sleep_ms = int(args.update_min_sleep_ms)
    update_backoff_ms = int(args.update_backoff_ms)
    update_max_retries = int(args.update_max_retries)
    max_equity_drawdown_pct = float(args.max_equity_drawdown_pct)
    free_cash_min_pct = float(args.free_cash_min_pct)
    risk_stop_policy = str(args.risk_stop_policy)
    sizing_mode = str(args.sizing_mode)
    risk_per_trade_pct = float(args.risk_per_trade_pct)
    ai_risk_min_pct = float(args.ai_risk_min_pct)
    ai_risk_max_pct = float(args.ai_risk_max_pct)
    max_leverage = float(args.max_leverage)
    scan_paths: Dict[str, str] = {}
    backtests: List[str] = []
    datasets: List[str] = []
    if args.cmd == "data:update":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        return 0
    if args.cmd == "scan":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        return 0
    if args.cmd == "backtest:top":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        return 0
    if args.cmd == "backtest:global":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        cmd_backtest_global(
            provider,
            run_dir,
            symbols,
            run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        return 0
    if args.cmd == "dataset:build":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        cmd_dataset_build(provider, symbols, run_tfs, entry_mode, workers)
        return 0
    if args.cmd == "report:setup-edge":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        cmd_report_setup_edge(run_dir, ds_paths, backtests)
        cmd_report_html(run_dir, backtests, datasets)
        return 0
    if args.cmd == "report:html":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        cmd_report_html(run_dir, backtests, datasets)
        return 0
    if args.cmd == "pipeline:report":
        print("updating data...")
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        print("scanning...")
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        print("backtesting...")
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        print("building datasets...")
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[:10]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        print("setup-edge report...")
        cmd_report_setup_edge(run_dir, ds_paths, backtests)
        print("html report...")
        cmd_report_html(run_dir, backtests, datasets)
        return 0
    if args.cmd == "pipeline:train":
        print("updating data...")
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        print("scanning...")
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        print("building datasets...")
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[:10]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": []})
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        print("training stack...")
        cmd_train_stack(run_dir, ds_paths)
        print("calibrating...")
        cmd_calibrate(run_dir, ds_paths)
        return 0
    if args.cmd == "train:stack":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": []})
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        cmd_train_stack(run_dir, ds_paths)
        return 0
    if args.cmd == "train:calibrate":
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        top_syms = pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[: _top_n()]
        datasets = cmd_dataset_build(provider, symbols=top_syms, tfs=run_tfs, entry_mode=entry_mode, workers=workers)
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": []})
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        cmd_calibrate(run_dir, ds_paths)
        return 0
    if args.cmd == "all":
        print("updating data...")
        cmd_data_update(provider, run_dir, symbols, update_tfs, update_workers, update_min_sleep_ms, update_backoff_ms, update_max_retries)
        print("scanning...")
        scan_paths = cmd_scan(provider, run_dir, symbols, run_tfs, entry_mode, workers)
        print("backtesting...")
        backtests = cmd_backtest_top(
            provider,
            run_dir,
            scan_paths,
            top_n=_top_n(),
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
            max_equity_drawdown_pct=max_equity_drawdown_pct,
            free_cash_min_pct=free_cash_min_pct,
            risk_stop_policy=risk_stop_policy,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            ai_risk_min_pct=ai_risk_min_pct,
            ai_risk_max_pct=ai_risk_max_pct,
            max_leverage=max_leverage,
        )
        print("building datasets...")
        datasets = cmd_dataset_build(
            provider,
            symbols=pick_top_symbols(_read_json(scan_paths.get("15m", ""), []), _top_n()) or symbols[:10],
            tfs=run_tfs,
            entry_mode=entry_mode,
            workers=workers,
        )
        print("writing datasets manifest...")
        _write_json(os.path.join(run_dir, "datasets_manifest.json"), {"datasets": datasets, "backtests": backtests})
        print("setting up report...")
        ds_paths = [str(d.get("path") or "") for d in datasets if int(d.get("rows") or 0) > 0 and str(d.get("path") or "")]
        cmd_report_setup_edge(run_dir, ds_paths, backtests)
        print("writing html report...")
        cmd_report_html(run_dir, backtests, datasets)
        print("training stack...")
        cmd_train_stack(run_dir, ds_paths)
        print("calibrating...")
        cmd_calibrate(run_dir, ds_paths)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
