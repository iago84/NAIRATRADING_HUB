from __future__ import annotations

import os
from typing import Dict, List


def render_html(title: str, sections: List[Dict[str, str]]) -> str:
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'/>",
        f"<title>{title}</title>",
        "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:980px;margin:40px auto;line-height:1.5}code,pre{background:#f6f6f6;padding:2px 4px;border-radius:4px}pre{padding:12px;overflow:auto}@media print{a{color:black;text-decoration:none}}</style>",
        "</head><body>",
        f"<h1>{title}</h1>",
    ]
    for s in sections:
        parts.append(f"<h2>{s['h']}</h2>")
        parts.append(s["p"])
    parts.append("</body></html>")
    return "\n".join(parts)


def write_html(path: str, html: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

