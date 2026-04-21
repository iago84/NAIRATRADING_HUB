from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass(frozen=True)
class LinRegMetrics:
    slope: float
    intercept: float
    r2: float
    slope_pct: float


def linreg_metrics(y: np.ndarray) -> LinRegMetrics:
    y = np.asarray(y, dtype=float)
    n = int(y.shape[0])
    if n < 2 or not np.isfinite(y).all():
        return LinRegMetrics(slope=0.0, intercept=float(y[-1]) if n else 0.0, r2=0.0, slope_pct=0.0)
    x = np.arange(n, dtype=float)
    xm = (n - 1) / 2.0
    ym = float(np.mean(y))
    denom = float(np.sum((x - xm) ** 2))
    if denom <= 0:
        return LinRegMetrics(slope=0.0, intercept=ym, r2=0.0, slope_pct=0.0)
    cov = float(np.sum((x - xm) * (y - ym)))
    slope = cov / denom
    intercept = ym - slope * xm
    yhat = intercept + slope * x
    ss_tot = float(np.sum((y - ym) ** 2))
    ss_res = float(np.sum((y - yhat) ** 2))
    r2 = 0.0 if ss_tot <= 0 else float(max(0.0, min(1.0, 1.0 - (ss_res / ss_tot))))
    slope_pct = 0.0 if abs(ym) <= 1e-12 else float((slope / ym) * 100.0)
    return LinRegMetrics(slope=slope, intercept=intercept, r2=r2, slope_pct=slope_pct)


def rolling_linreg_slope_pct(series: np.ndarray, window: int) -> Tuple[np.ndarray, np.ndarray]:
    y = np.asarray(series, dtype=float)
    n = int(y.shape[0])
    w = int(window)
    slope_pct = np.full(n, np.nan, dtype=float)
    r2 = np.full(n, np.nan, dtype=float)
    if w < 2 or n < w:
        return slope_pct, r2
    for i in range(w - 1, n):
        seg = y[i - w + 1 : i + 1]
        if not np.isfinite(seg).all():
            continue
        m = linreg_metrics(seg)
        slope_pct[i] = m.slope_pct
        r2[i] = m.r2
    return slope_pct, r2
