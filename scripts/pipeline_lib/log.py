from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str, *, verbose: bool = False) -> None:
    silent = str(os.getenv("PIPELINE_SILENT", "")).strip()
    if silent:
        return
    if verbose or str(os.getenv("PIPELINE_VERBOSE", "")).strip():
        sys.stderr.write(f"[{_ts()}] {msg}\n")
        sys.stderr.flush()


def info(msg: str) -> None:
    silent = str(os.getenv("PIPELINE_SILENT", "")).strip()
    if silent:
        return
    sys.stderr.write(f"[{_ts()}] {msg}\n")
    sys.stderr.flush()

