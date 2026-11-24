"""Active risk against a benchmark: tracking error, beta, correlation, information ratio. Ported from v0.4.2."""

from __future__ import annotations

import math

import numpy as np

from .data import Series

MIN_MONTHS = 6


def active_risk(rp: np.ndarray, months: list[str], bm: Series | None, z: float) -> dict | None:
    if bm is None:
        return None
    idx = [t for t, ym in enumerate(months) if ym in bm.ret]
    p = rp[idx]
    b = np.array([bm.ret[months[t]] for t in idx])
    if len(idx) < MIN_MONTHS:
        return {"n": len(idx)}
    a = p - b
    vb = float(b.var(ddof=1))
    sa = float(a.std(ddof=1))
    return {
        "n": len(idx),
        "te": sa * math.sqrt(12),
        "beta": float(np.cov(p, b, ddof=1)[0, 1] / vb) if vb > 0 else 0.0,
        "corr": float(np.corrcoef(p, b)[0, 1]) if vb > 0 and p.std() > 0 else 0.0,
        "bm_vol_a": math.sqrt(vb * 12),
        "p_vol_a": float(p.std(ddof=1)) * math.sqrt(12),
        "active_mean_a": float(a.mean()) * 12,
        "ir": float(a.mean()) * 12 / (sa * math.sqrt(12)) if sa > 0 else 0.0,
        "rel_var": z * sa,
        "bm_var": z * math.sqrt(vb),
    }
