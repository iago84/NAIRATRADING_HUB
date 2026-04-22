from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List


def load_scan_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        v = json.loads(f.read() or "[]")
    return list(v or [])


def load_random_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = (line or "").strip()
            if not s:
                continue
            out.append(dict(json.loads(s)))
    return out


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
    ap.add_argument("--out-md", default="")
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    scan_items: List[Dict[str, Any]] = []
    random_items: List[Dict[str, Any]] = []
    if str(args.scan_json).strip():
        scan_items = load_scan_json(str(args.scan_json))
    if str(args.random_jsonl).strip():
        random_items = load_random_jsonl(str(args.random_jsonl))

    md = build_markdown_report(scan_items, random_items)
    if str(args.out_md).strip():
        os.makedirs(os.path.dirname(str(args.out_md)) or ".", exist_ok=True)
        with open(str(args.out_md), "w", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)

    if str(args.out_json).strip():
        payload = {"scan": scan_items, "random": random_items, "markdown": md}
        os.makedirs(os.path.dirname(str(args.out_json)) or ".", exist_ok=True)
        with open(str(args.out_json), "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

