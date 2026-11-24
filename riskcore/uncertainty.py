"""How much to trust a risk number (new in v2; spec Section 5.3).

Two tools: a range for headline measures (bootstrap) and a plain confidence label
based on how much of the estimate rests on the holdings' own reported data.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def vol_standard_error(sd: float, n: int) -> float:
    """Approximate standard error of a sample standard deviation under normality: sd / sqrt(2(n-1))."""
    return sd / math.sqrt(2 * (n - 1)) if n > 1 else float("nan")


def bootstrap_interval(
    r: np.ndarray, stat: Callable[[np.ndarray], float], n_boot: int = 2000, level: float = 0.90, seed: int = 20261124,
    block: int = 3,
) -> tuple[float, float]:
    """Moving-block bootstrap interval for a statistic of a return series.

    Blocks of `block` months keep some autocorrelation. Seeded, so results are reproducible.
    """
    r = np.asarray(r, float)
    T = len(r)
    if T < 2 * block:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nb = math.ceil(T / block)
    vals = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, T - block + 1, nb)
        sample = np.concatenate([r[s : s + block] for s in starts])[:T]
        vals[b] = stat(sample)
    lo, hi = np.quantile(vals, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def confidence_label(months: int, own_share: float, uses_desmoothing_or_proxy_share: float = 0.0, stale_share: float = 0.0) -> str:
    """'High', 'Medium' or 'Low' (spec Section 5.3).

    own_share: weight-averaged share of the estimation matrix that is the holdings' own reported data.
    stale_share: portfolio weight in holdings whose reported returns are mostly zero (stale-priced),
    which make risk look lower than it is even though the data is 'reported'.
    """
    if months < 36 or own_share < 0.6 or uses_desmoothing_or_proxy_share > 0.5 or stale_share > 0.25:
        return "Low"
    if months >= 60 and own_share >= 0.95 and uses_desmoothing_or_proxy_share == 0 and stale_share <= 0.05:
        return "High"
    return "Medium"
