"""Factor exposures (OLS betas) and principal component analysis. Ported from v0.4.2."""

from __future__ import annotations

import numpy as np

from .data import Series
from .risk import covariance


def ols(y: np.ndarray, F: np.ndarray) -> dict:
    """Regress y on an intercept plus the columns of F."""
    G = np.column_stack([np.ones(len(y)), F])
    coef, *_ = np.linalg.lstsq(G, y, rcond=None)
    res = y - G @ coef
    tss = float(((y - y.mean()) ** 2).sum())
    return {"alpha": float(coef[0]), "beta": coef[1:], "r2": 1 - float(res @ res) / tss if tss > 0 else 0.0}


def min_factor_months(k: int) -> int:
    return max(8, k + 3)


def factor_exposures(
    X: np.ndarray, w: np.ndarray, rp: np.ndarray, months: list[str], factors: list[Series], bench: Series | None,
    sleeve_idx: np.ndarray, sleeve_w: np.ndarray,
) -> dict | None:
    if not factors:
        return None
    K = len(factors)
    idx = [t for t, ym in enumerate(months) if all(ym in f.ret for f in factors)]
    if len(idx) < min_factor_months(K):
        return None
    F = np.array([[f.ret[months[t]] for f in factors] for t in idx])
    fits = [ols(X[idx, i], F) for i in range(X.shape[1])]
    B = np.array([f["beta"] for f in fits])
    bp = w @ B
    port = ols(rp[idx], F)
    SF = covariance(F)
    bb = None
    if bench is not None:
        bi = [t for t in idx if months[t] in bench.ret]
        if len(bi) >= min_factor_months(K):
            bb = ols(np.array([bench.ret[months[t]] for t in bi]), np.array([[f.ret[months[t]] for f in factors] for t in bi]))
    S = len(sleeve_w)
    sleeve_b = np.zeros((S, K))
    for i in range(len(w)):
        s = sleeve_idx[i]
        if sleeve_w[s] > 0:
            sleeve_b[s] += w[i] / sleeve_w[s] * B[i]
    return {
        "names": [f.name for f in factors],
        "n": len(idx),
        "B": B,
        "r2": np.array([f["r2"] for f in fits]),
        "port": bp,
        "port_r2": port["r2"],
        "alpha_m": port["alpha"],
        "bench": bb["beta"] if bb else None,
        "bench_r2": bb["r2"] if bb else None,
        "SF": SF,
        "sleeve": sleeve_b,
        "vol_a": np.sqrt(np.diag(SF) * 12),
    }


def pca(C: np.ndarray, w: np.ndarray, max_components: int = 5) -> dict | None:
    """Principal components of the holdings' covariance; share of total variance and of portfolio variance."""
    act = [i for i in range(C.shape[0]) if C[i, i] > 1e-14]
    if len(act) < 2:
        return None
    sub = C[np.ix_(act, act)]
    ev, vec = np.linalg.eigh(sub)
    o = np.argsort(-ev)
    ev, vec = ev[o], vec[:, o]
    tot = float(np.clip(ev, 0, None).sum())
    var_p = float(w @ C @ w)
    comps = []
    for k in range(min(max_components, len(act))):
        lam = max(float(ev[k]), 0.0)
        proj = float(vec[:, k] @ w[act])
        comps.append({"share": lam / tot if tot > 0 else 0.0, "port_share": lam * proj * proj / var_p if var_p > 0 else 0.0, "vector": vec[:, k], "holdings": act})
    return {"comps": comps, "n": len(act)}
