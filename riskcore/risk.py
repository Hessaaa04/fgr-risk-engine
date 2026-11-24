"""Volatility, VaR and Expected Shortfall, drawdown and risk decomposition.

Ported from v0.4.2. Conventions: monthly returns; 'A' suffix = annualised
by sqrt(12); VaR and ES are positive numbers meaning a loss; parametric
figures assume a normal distribution with zero mean (as v0.4.2 does).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from .estimation import EstimationInput, Lineage

STALE_ZERO_SHARE = 0.7  # a holding is 'stale' when >= 70% of its own months show exactly 0


def covariance(X: np.ndarray) -> np.ndarray:
    """Sample covariance (n - 1 denominator), columns = assets."""
    if X.shape[0] < 2:
        return np.zeros((X.shape[1], X.shape[1]))
    return np.atleast_2d(np.cov(X, rowvar=False, ddof=1))


def corr_from_cov(C: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.clip(np.diag(C), 0, None))
    out = np.zeros_like(C)
    nz = d > 0
    out[np.ix_(nz, nz)] = C[np.ix_(nz, nz)] / np.outer(d[nz], d[nz])
    np.fill_diagonal(out, 1.0)
    return out


def max_drawdown(r: np.ndarray) -> float:
    """Largest peak-to-trough fall of the compounded series, measured from a starting level of 1."""
    peak = lvl = 1.0
    mdd = 0.0
    for x in r:
        lvl *= 1 + x
        peak = max(peak, lvl)
        mdd = min(mdd, lvl / peak - 1)
    return mdd


def parametric_var_es(sd: float, conf: float) -> tuple[float, float, float]:
    """(z, VaR, ES) for a zero-mean normal with standard deviation sd."""
    z = float(stats.norm.ppf(conf))
    return z, z * sd, sd * float(stats.norm.pdf(z)) / (1 - conf)


def historical_var_es(r: np.ndarray, conf: float) -> tuple[float, float]:
    """Empirical VaR (linear-interpolated quantile, as numpy) and the mean loss at or beyond it."""
    q = float(np.quantile(r, 1 - conf))
    return -q, -float(r[r <= q].mean())


@dataclass
class RiskResult:
    vol_m: float
    vol_a: float
    conf: float
    z: float
    var: float
    es: float
    hist_var: float | None
    hist_es: float | None
    max_dd: float
    mean_m: float
    rp: np.ndarray
    C: np.ndarray
    holdings: list[dict]
    sleeves: list[dict]
    XS: np.ndarray
    CS: np.ndarray
    sleeve_w: np.ndarray


def analyse_risk(inp: EstimationInput, conf: float = 0.95) -> RiskResult:
    X, w = inp.X, inp.w
    T, N = X.shape
    C = covariance(X)
    Cw = C @ w
    var_p = float(w @ Cw)
    sd = math.sqrt(max(var_p, 0.0))
    rp = X @ w
    z, VaR, ES = parametric_var_es(sd, conf)
    hv = he = None
    if T >= 24:
        hv, he = historical_var_es(rp, conf)

    holdings = []
    for i, h in enumerate(inp.positions):
        w2 = w.copy()
        w2[i] = 0
        own = [inp.lineage[t][i] in (Lineage.REPORTED, Lineage.PROXY) for t in range(T)]
        real = sum(own)
        zeros = sum(1 for t in range(T) if own[t] and X[t, i] == 0)
        proxied = any(inp.lineage[t][i] == Lineage.PROXY for t in range(T))
        sdi = math.sqrt(max(C[i, i], 0.0))
        holdings.append(
            {
                "name": h.name,
                "sleeve": inp.sleeves[inp.sleeve_idx[i]],
                "liquid": h.liquid,
                "value": float(inp.values[i]),
                "w": float(w[i]),
                "vol_a": sdi * math.sqrt(12),
                "rc": float(w[i] * Cw[i] / var_p) if var_p > 0 else 0.0,
                "mvar": float(z * Cw[i] / sd) if sd > 0 else 0.0,
                "cvar": float(w[i] * z * Cw[i] / sd) if sd > 0 else 0.0,
                "ivar": VaR - z * math.sqrt(max(float(w2 @ C @ w2), 0.0)),
                "real": real,
                "filled": T - real,
                "stale": real > 0 and zeros / real >= STALE_ZERO_SHARE and not proxied,
                "no_data": real == 0,
                "proxied": proxied,
            }
        )

    S = len(inp.sleeves)
    sw = np.array([w[inp.sleeve_idx == s].sum() for s in range(S)])
    XS = np.column_stack(
        [X[:, inp.sleeve_idx == s] @ (w[inp.sleeve_idx == s] / sw[s]) if sw[s] > 0 else np.zeros(T) for s in range(S)]
    ) if S else np.zeros((T, 0))
    CS = covariance(XS)
    sleeves = []
    for s, name in enumerate(inp.sleeves):
        hs = [h for h in holdings if h["sleeve"] == name]
        sleeves.append(
            {
                "name": name,
                "w": float(sw[s]),
                "rc": sum(h["rc"] for h in hs),
                "cvar": sum(h["cvar"] for h in hs),
                "vol_a": math.sqrt(max(CS[s, s], 0.0) * 12),
                "illiquid_w": sum(h["w"] for h in hs if not h["liquid"]),
                "n": len(hs),
            }
        )
    return RiskResult(
        vol_m=sd,
        vol_a=sd * math.sqrt(12),
        conf=conf,
        z=z,
        var=VaR,
        es=ES,
        hist_var=hv,
        hist_es=he,
        max_dd=max_drawdown(rp),
        mean_m=float(rp.mean()) if T else 0.0,
        rp=rp,
        C=C,
        holdings=holdings,
        sleeves=sleeves,
        XS=XS,
        CS=CS,
        sleeve_w=sw,
    )


def liquidity(holdings: list[dict], target: float = 0.90) -> dict:
    """Share of value flagged liquid, against a target. A coarse measure: see the spec, Section 5.1."""
    liq = sum(h["w"] for h in holdings if h["liquid"])
    return {"liquid": liq, "target": target, "shortfall": max(0.0, target - liq)}
