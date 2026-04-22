from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelinePaths:
    repo_root: str
    data_dir: str

    @property
    def history_dir(self) -> str:
        return os.path.join(self.data_dir, "history")

    @property
    def reports_dir(self) -> str:
        return os.path.join(self.data_dir, "reports")

    @property
    def docs_generated_dir(self) -> str:
        return os.path.join(self.repo_root, "docs", "generated")

