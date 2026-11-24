"""Corrections for smoothed and stale reported returns (new in v2; spec Section 5.2).

Reported returns of property, private and many hedge funds are smoothed: each
month blends the true change with earlier ones, which understates volatility
and correlation. These functions are estimates with real uncertainty and must
be labelled wherever used.
"""

from __future__ import annotations

import numpy as np

MIN_MONTHS = 36
PHI_CAP = 0.9


def ar1(r: np.ndarray) -> float:
    """First-order autocorrelation of a return series."""
    r = np.asarray(r, float)
    if len(r) < 3 or r.std() == 0:
        return 0.0
    x, y = r[:-1] - r.mean(), r[1:] - r.mean()
    return float((x @ y) / ((r - r.mean()) @ (r - r.mean())))


def geltner(r: np.ndarray, phi: float | None = None) -> tuple[np.ndarray, float]:
    """Desmooth a monthly return series: r_true_t = (r_obs_t - phi r_obs_{t-1}) / (1 - phi).

    phi is estimated from the data unless given. Requires at least 36 months; phi is
    capped at 0.9 and floored at 0 (negative autocorrelation is not smoothing).
    Returns (desmoothed series, phi used). The first month is dropped.
    """
    r = np.asarray(r, float)
    if len(r) < MIN_MONTHS:
        raise ValueError(f"Desmoothing needs at least {MIN_MONTHS} months; got {len(r)}.")
    if phi is None:
        phi = ar1(r)
    phi = float(min(max(phi, 0.0), PHI_CAP))
    return (r[1:] - phi * r[:-1]) / (1 - phi), phi


def smooth(r: np.ndarray, phi: float) -> np.ndarray:
    """Inverse of geltner: apply AR(1) appraisal smoothing (used to build synthetic data and tests)."""
    r = np.asarray(r, float)
    out = np.empty_like(r)
    prev = r[0]
    for t, x in enumerate(r):
        prev = (1 - phi) * x + phi * prev if t else x
        out[t] = prev
    return out


def observed_frequency(r: dict[str, float], zero_tol: float = 0.0005) -> str:
    """Guess how often a holding is revalued from where its non-zero returns fall.

    Returns of size below `zero_tol` (5bp) count as zero, so small monthly accruals between
    revaluations do not hide a quarterly or annual pattern. 'annual' when at least 80% of
    non-zero returns land in one calendar month; 'quarterly' when at least 80% land in one of the
    three month-of-quarter classes (any phase: Mar/Jun/Sep/Dec or Feb/May/Aug/Nov ...);
    otherwise 'monthly'. Needs 8+ non-zero months; else 'unknown'. A label only: an
    instrument's recorded valuation frequency overrides it, and 'unknown' never clears a stale flag.
    """
    nz = [m for m, x in r.items() if x is not None and abs(x) >= zero_tol]
    if len(nz) < 8:
        return "unknown"
    months = [int(m[5:7]) for m in nz]
    top = max(months.count(k) for k in range(1, 13))
    if top / len(nz) >= 0.8 and len(nz) <= len(r) / 6:
        return "annual"
    q = max(sum(1 for k in months if k % 3 == c) for c in range(3))
    if q / len(nz) >= 0.8 and len(nz) <= len(r) / 2:
        return "quarterly"
    return "monthly"
