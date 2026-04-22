from __future__ import annotations

from typing import List


def trend_age_bars_from_directions(dirs: List[str]) -> int:
    if not dirs:
        return 0
    last = str(dirs[-1] or "neutral")
    if last == "neutral":
        return 0
    run = 0
    for d in reversed(dirs):
        if str(d or "neutral") != last:
            break
        run += 1
    return int(run)

