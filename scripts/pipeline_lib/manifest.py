from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(path: str) -> Dict[str, Any]:
    st = os.stat(path)
    return {"path": path, "size": int(st.st_size), "sha256": sha256_file(path)}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Manifest:
    job_id: str
    command: str
    args: Dict[str, Any]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    created_at: str
    git_head: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "command": self.command,
            "args": self.args,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "git_head": self.git_head,
        }


def write_manifest(path: str, manifest: Manifest) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))

