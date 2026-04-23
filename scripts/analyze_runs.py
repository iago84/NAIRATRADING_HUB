from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from scripts.pipeline_lib.log import info, log
from scripts.pipeline_lib.docs_gen import render_html, write_html


def load_scan_json(path: str) -> List[Dict[str, Any]]:
    log(f"load_scan_json path={path}", verbose=False)
    with open(path, "r", encoding="utf-8") as f:
        v = json.loads(f.read() or "[]")
    return list(v or [])


def load_random_jsonl(path: str) -> List[Dict[str, Any]]:
    log(f"load_random_jsonl path={path}", verbose=False)
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = (line or "").strip()
            if not s:
                continue
            out.append(dict(json.loads(s)))
    return out


def load_dataset_csv(path: str) -> List[Dict[str, Any]]:
    log(f"load_dataset_csv path={path}", verbose=False)
    df = pd.read_csv(path)
    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        d = row.to_dict()
        d["_source"] = "dataset_csv"
        d["_path"] = str(path)
        out.append(d)
    return out


def load_backtest_json(path: str) -> List[Dict[str, Any]]:
    log(f"load_backtest_json path={path}", verbose=False)
    with open(path, "r", encoding="utf-8") as f:
        obj = json.loads(f.read() or "{}")
    trades = obj.get("trades") or []
    out: List[Dict[str, Any]] = []
    for t in trades:
        d = dict(t)
        d["_source"] = "backtest_json"
        d["_path"] = str(path)
        out.append(d)
    return out


def summarize_dataset_csv(path: str) -> Dict[str, Any]:
    try:
        df = pd.read_csv(path)
        rows = int(len(df))
        pnl_col = pd.to_numeric(df.get("pnl"), errors="coerce") if "pnl" in df.columns else pd.Series([0.0] * rows, dtype=float)
        pnl_col = pnl_col.fillna(0.0)
        win_col = pd.to_numeric(df.get("win"), errors="coerce") if "win" in df.columns else None
        if win_col is not None:
            wins = int((win_col.fillna(0.0) > 0.0).sum())
        else:
            wins = int((pnl_col > 0.0).sum())
        return {
            "path": str(path),
            "rows": rows,
            "avg_pnl": float(pnl_col.mean()) if rows else 0.0,
            "win_rate_pct": (float(wins) / max(1, rows)) * 100.0,
        }
    except Exception as e:
        return {"path": str(path), "error": type(e).__name__}


def summarize_backtest_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read() or "{}")
        m = obj.get("metrics") or {}
        trades = int(m.get("trades") or 0)
        total_pnl = float(m.get("total_pnl") or 0.0)
        dd = float(m.get("max_drawdown_pct") or 0.0)
        timing_blocks = int(m.get("gates_timing_blocked") or 0)
        return {
            "path": str(path),
            "trades": trades,
            "total_pnl": total_pnl,
            "pnl_per_trade": (float(total_pnl) / max(1, trades)) if trades else 0.0,
            "max_drawdown_pct": dd,
            "gates_timing_blocked": timing_blocks,
        }
    except Exception as e:
        return {"path": str(path), "error": type(e).__name__}


def normalize_trade_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        setup = str(r.get("setup_primary") or ((r.get("entry_meta") or {}).get("setup_primary") if isinstance(r.get("entry_meta"), dict) else "") or "unknown")
        try:
            pnl = float(r.get("pnl") or 0.0)
        except Exception:
            pnl = 0.0
        risk_r = None
        try:
            em = r.get("entry_meta")
            if isinstance(em, dict) and em.get("risk_r") is not None:
                risk_r = float(em.get("risk_r"))
        except Exception:
            risk_r = None
        try:
            feats = r.get("_features")
            if risk_r is None and isinstance(feats, dict) and feats.get("risk_r") is not None:
                risk_r = float(feats.get("risk_r"))
        except Exception:
            pass
        R = None
        if risk_r is not None and float(risk_r) > 0:
            R = float(pnl) / float(risk_r)
        def _i(k: str) -> Optional[int]:
            try:
                v = r.get(k)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return None
                return int(v)
            except Exception:
                return None
        def _f(k: str) -> Optional[float]:
            try:
                v = r.get(k)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return None
                return float(v)
            except Exception:
                return None
        out.append(
            {
                "setup_primary": setup,
                "pnl": float(pnl),
                "risk_r": float(risk_r) if risk_r is not None else None,
                "R": float(R) if R is not None else None,
                "trend_age_bars": _i("trend_age_bars"),
                "ema_compression": _f("ema_compression"),
            }
        )
    return out


def aggregate_by_setup(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows or []:
        k = str(r.get("setup_primary") or "unknown")
        by.setdefault(k, []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for k, items in by.items():
        pnls = [float(x.get("pnl") or 0.0) for x in items]
        wins = [1 if float(x.get("pnl") or 0.0) > 0 else 0 for x in items]
        Rs = [x.get("R") for x in items]
        Rs2 = [float(x) for x in Rs if x is not None]
        def _med(a: List[float]) -> float:
            if not a:
                return 0.0
            s = sorted(a)
            m = len(s) // 2
            return float(s[m]) if len(s) % 2 == 1 else float((s[m - 1] + s[m]) / 2.0)
        out[k] = {
            "n_trades": int(len(items)),
            "win_rate_pct": (float(sum(wins)) / max(1, len(items))) * 100.0,
            "avg_pnl": float(sum(pnls)) / max(1, len(pnls)),
            "median_pnl": _med(pnls),
            "avg_R": (float(sum(Rs2)) / max(1, len(Rs2))) if Rs2 else None,
            "median_R": _med(Rs2) if Rs2 else None,
        }
    return out


def _escape(x: Any) -> str:
    return _html.escape(str(x))


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{_escape(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = "".join(f"<td>{_escape(c)}</td>" for c in r)
        trs.append(f"<tr>{tds}</tr>")
    return (
        "<table style='border-collapse:collapse;width:100%'>"
        f"<thead><tr>{th}</tr></thead>"
        "<tbody>"
        + "".join(trs)
        + "</tbody></table>"
    )


def _count(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for it in items or []:
        v = str(it.get(key) or "")
        if not v:
            v = "unknown"
        out[v] = int(out.get(v, 0)) + 1
    return out


def build_markdown_report(scan_items: List[Dict[str, Any]], random_items: List[Dict[str, Any]]) -> str:
    scan_n = len(scan_items or [])
    rnd_n = len(random_items or [])
    dirs = _count(scan_items, "direction")
    kinds = _count(scan_items, "entry_kind")
    total_pnl = 0.0
    total_trades = 0
    for r in random_items or []:
        m = r.get("metrics") or {}
        try:
            total_pnl += float(m.get("total_pnl") or 0.0)
        except Exception:
            pass
        try:
            total_trades += int(m.get("trades") or 0)
        except Exception:
            pass
    exp = float(total_pnl) / max(1, int(total_trades))
    lines = []
    lines.append("# Reporte: scan + random_backtests")
    lines.append("")
    lines.append("## Scan")
    lines.append(f"- items: {scan_n}")
    lines.append(f"- direction_counts: {json.dumps(dirs, ensure_ascii=False)}")
    lines.append(f"- entry_kind_counts: {json.dumps(kinds, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Random Backtests")
    lines.append(f"- runs: {rnd_n}")
    lines.append(f"- total_trades: {int(total_trades)}")
    lines.append(f"- total_pnl: {float(total_pnl):.6f}")
    lines.append(f"- expectancy_per_trade: {float(exp):.6f}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-json", default="")
    ap.add_argument("--random-jsonl", default="")
    ap.add_argument("--dataset-csv", action="append", default=[])
    ap.add_argument("--backtest-json", action="append", default=[])
    ap.add_argument("--dataset-dir", default="")
    ap.add_argument("--out-md", default="")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-html", default="")
    args = ap.parse_args()
    info("analyze_runs start")

    scan_items: List[Dict[str, Any]] = []
    random_items: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []
    dataset_summaries: List[Dict[str, Any]] = []
    backtest_summaries: List[Dict[str, Any]] = []
    if str(args.scan_json).strip():
        scan_items = load_scan_json(str(args.scan_json))
    if str(args.random_jsonl).strip():
        random_items = load_random_jsonl(str(args.random_jsonl))
    for p in list(args.dataset_csv or []):
        if str(p).strip():
            trade_rows += load_dataset_csv(str(p))
            dataset_summaries.append(summarize_dataset_csv(str(p)))
    for p in list(args.backtest_json or []):
        if str(p).strip():
            trade_rows += load_backtest_json(str(p))
            backtest_summaries.append(summarize_backtest_json(str(p)))
    ds_dir = str(args.dataset_dir or "").strip()
    if ds_dir:
        try:
            for fn in sorted(os.listdir(ds_dir)):
                if not fn.endswith(".csv"):
                    continue
                p = os.path.join(ds_dir, fn)
                dataset_summaries.append(summarize_dataset_csv(p))
        except Exception:
            pass
    info(f"inputs scan={len(scan_items)} random={len(random_items)} trades_raw={len(trade_rows)}")

    md = build_markdown_report(scan_items, random_items)
    if trade_rows:
        norm = normalize_trade_rows(trade_rows)
        agg = aggregate_by_setup(norm)
        md += "## Setup Edge\n"
        for k, v in sorted(agg.items(), key=lambda kv: int(kv[1].get("n_trades") or 0), reverse=True):
            md += f"- {k}: n={v['n_trades']} win%={v['win_rate_pct']:.1f} avg_pnl={v['avg_pnl']:.6f} avg_R={v.get('avg_R')}\n"
        md += "\n"
    if dataset_summaries:
        md += "## Datasets\n"
        ds_ok = [d for d in dataset_summaries if not d.get("error")]
        ds_ok.sort(key=lambda x: float(x.get("avg_pnl") or 0.0), reverse=True)
        for d in ds_ok[:50]:
            md += f"- {os.path.basename(str(d.get('path') or ''))}: rows={d.get('rows')} avg_pnl={d.get('avg_pnl')} win%={d.get('win_rate_pct')}\n"
        md += "\n"
    if backtest_summaries:
        md += "## Backtests\n"
        bt_ok = [b for b in backtest_summaries if not b.get("error")]
        bt_ok.sort(key=lambda x: float(x.get("pnl_per_trade") or 0.0), reverse=True)
        for b in bt_ok[:50]:
            md += f"- {os.path.basename(str(b.get('path') or ''))}: trades={b.get('trades')} pnl/trade={b.get('pnl_per_trade')} total_pnl={b.get('total_pnl')} dd={b.get('max_drawdown_pct')}\n"
        md += "\n"
    if str(args.out_md).strip():
        os.makedirs(os.path.dirname(str(args.out_md)) or ".", exist_ok=True)
        with open(str(args.out_md), "w", encoding="utf-8") as f:
            f.write(md)
        info(f"wrote md={args.out_md}")
    else:
        print(md)

    if str(args.out_json).strip():
        payload = {"scan": scan_items, "random": random_items, "markdown": md}
        if trade_rows:
            payload["setup_edge"] = aggregate_by_setup(normalize_trade_rows(trade_rows))
        if dataset_summaries:
            payload["datasets"] = dataset_summaries
        if backtest_summaries:
            payload["backtests"] = backtest_summaries
        os.makedirs(os.path.dirname(str(args.out_json)) or ".", exist_ok=True)
        with open(str(args.out_json), "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        info(f"wrote json={args.out_json}")
    if str(args.out_html).strip():
        sections: List[Dict[str, str]] = []
        if dataset_summaries:
            ok = [d for d in dataset_summaries if not d.get("error")]
            ok.sort(key=lambda x: int(x.get("rows") or 0), reverse=True)
            rows = [[os.path.basename(str(d.get("path") or "")), d.get("rows"), f"{float(d.get('avg_pnl') or 0.0):.6f}", f"{float(d.get('win_rate_pct') or 0.0):.1f}"] for d in ok[:50]]
            sections.append({"h": "Datasets", "p": _table(["file", "rows", "avg_pnl", "win%"], rows) if rows else "<p>no datasets</p>"})
        if backtest_summaries:
            ok2 = [b for b in backtest_summaries if not b.get("error")]
            ok2.sort(key=lambda x: float(x.get("pnl_per_trade") or 0.0), reverse=True)
            rows2 = [
                [
                    os.path.basename(str(b.get("path") or "")),
                    b.get("trades"),
                    f"{float(b.get('pnl_per_trade') or 0.0):.6f}",
                    f"{float(b.get('total_pnl') or 0.0):.6f}",
                    f"{float(b.get('max_drawdown_pct') or 0.0):.2f}",
                ]
                for b in ok2[:50]
            ]
            timing_total = sum(int(b.get("gates_timing_blocked") or 0) for b in ok2)
            p = f"<p>Timing gate blocks: {int(timing_total)}</p>" + (_table(["file", "trades", "pnl/trade", "total_pnl", "dd%"], rows2) if rows2 else "<p>no backtests</p>")
            sections.append({"h": "Backtests", "p": p})
        html = render_html("Setup Edge", sections or [{"h": "Resumen", "p": "<p>sin datos</p>"}])
        write_html(str(args.out_html), html)
        info(f"wrote html={args.out_html}")
    info("analyze_runs done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
