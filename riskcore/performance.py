"""Realised performance of the portfolio and of comparison indices (new in v2).

All figures use the portfolio's actual month-by-month returns (value-weighted by
start-of-month value, external flows such as oil contributions excluded), not the
'current weights through history' series used for forward-looking risk.
Missing is None: a comparison only uses months where both sides have a return.
"""

from __future__ import annotations

import math

import numpy as np

from .risk import max_drawdown


def _compound(x) -> float:
    return float(np.prod(1 + np.asarray(x, float)) - 1)


def annualise(total: float, months: int) -> float | None:
    """Geometric annualised return from a compounded total over `months` months."""
    if months <= 0 or total <= -1:
        return None
    return (1 + total) ** (12 / months) - 1


def series_stats(r: np.ndarray) -> dict:
    """Return, volatility, drawdown and best/worst month of one monthly return series.

    Periods shorter than 12 months are not annualised (GIPS practice): ann_return is None.
    """
    r = np.asarray(r, float)
    n = len(r)
    tot = _compound(r)
    return {
        "n": n,
        "total": tot,
        "ann_return": annualise(tot, n) if n >= 12 else None,
        "vol_a": float(r.std(ddof=1)) * math.sqrt(12) if n > 1 else None,
        "max_dd": max_drawdown(r) if n else None,
        "best": float(r.max()) if n else None,
        "worst": float(r.min()) if n else None,
        "pos_share": float((r > 0).mean()) if n else None,
    }


def compare(port: dict[str, float | None], bench: dict[str, float], months: list[str]) -> dict | None:
    """Portfolio against one benchmark over `months` (only months where both have a return).

    Tracking error = annualised standard deviation of (portfolio - benchmark).
    Information ratio = annualised mean active return / tracking error.
    Up/down capture = portfolio's compounded return over the benchmark's up (down) months as a share of the
    benchmark's compounded return over the same months (the usual fact-sheet convention).
    """
    ms = [m for m in months if port.get(m) is not None and bench.get(m) is not None]
    if len(ms) < 6:
        return {"n": len(ms)}
    p = np.array([port[m] for m in ms], float)
    b = np.array([bench[m] for m in ms], float)
    a = p - b
    vb = float(b.var(ddof=1))
    te = float(a.std(ddof=1)) * math.sqrt(12)
    up, dn = b > 0, b < 0
    out = {
        "n": len(ms),
        "from": ms[0],
        "to": ms[-1],
        "port": series_stats(p),
        "bench": series_stats(b),
        "excess_total": _compound(p) - _compound(b),
        "te": te,
        "beta": float(np.cov(p, b, ddof=1)[0, 1] / vb) if vb > 0 else None,
        "corr": float(np.corrcoef(p, b)[0, 1]) if vb > 0 and p.std() > 0 else None,
        "ir": float(a.mean()) * 12 / te if te > 0 else None,
        "hit_rate": float((a > 0).mean()),
        "up_capture": _compound(p[up]) / _compound(b[up]) if up.sum() >= 3 else None,
        "down_capture": _compound(p[dn]) / _compound(b[dn]) if dn.sum() >= 3 else None,
    }
    return out


def cumulative(r: dict[str, float | None], months: list[str]) -> list[float | None]:
    """Growth of 1 over `months`; None from the first missing month onwards."""
    out, lvl, broken = [], 1.0, False
    for m in months:
        x = r.get(m)
        if x is None or broken:
            broken = True
            out.append(None)
            continue
        lvl *= 1 + x
        out.append(lvl)
    return out


def rolling_vol(r: dict[str, float | None], months: list[str], window: int = 36) -> list[float | None]:
    """Trailing `window`-month annualised volatility at each month (None until a full window exists)."""
    out = []
    for i in range(len(months)):
        if i + 1 < window:
            out.append(None)
            continue
        xs = [r.get(m) for m in months[i + 1 - window : i + 1]]
        out.append(None if any(x is None for x in xs) else float(np.std(xs, ddof=1)) * math.sqrt(12))
    return out
