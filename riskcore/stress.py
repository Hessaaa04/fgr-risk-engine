"""Factor stress tests, conditional propagation and the reverse stress test. Ported from v0.4.2.

A holding's shock = its factor betas x the factor moves. This captures only what
the factors explain, not fund-specific surprises, and understates stale-priced
holdings unless their betas are corrected (spec Section 5.2).
"""

from __future__ import annotations

import math

import numpy as np

from .calendar import ym_range
from .data import Series, norm

# Approximate factor moves, used only when loaded history does not cover the period.
SCENARIOS: list[dict] = [
    {"id": "gfc", "name": "2008 financial crisis", "kind": "historical", "from": "2007-11", "to": "2009-02",
     "preset": {"globalequities": -0.54, "ustreasuries": 0.14, "highyieldcredit": -0.26, "usdollar": 0.15, "oil": -0.49}},
    {"id": "euro", "name": "2011 euro crisis", "kind": "historical", "from": "2011-05", "to": "2011-09",
     "preset": {"globalequities": -0.195, "ustreasuries": 0.078, "highyieldcredit": -0.065, "usdollar": 0.076, "oil": -0.18}},
    {"id": "q418", "name": "Q4 2018 sell-off", "kind": "historical", "from": "2018-10", "to": "2018-12",
     "preset": {"globalequities": -0.134, "ustreasuries": 0.026, "highyieldcredit": -0.045, "usdollar": 0.011, "oil": -0.35}},
    {"id": "covid", "name": "2020 Covid sell-off", "kind": "historical", "from": "2020-02", "to": "2020-03",
     "preset": {"globalequities": -0.205, "ustreasuries": 0.056, "highyieldcredit": -0.127, "usdollar": 0.017, "oil": -0.61}},
    {"id": "y2022", "name": "2022 inflation and rates shock", "kind": "historical", "from": "2022-01", "to": "2022-09",
     "preset": {"globalequities": -0.254, "ustreasuries": -0.131, "highyieldcredit": -0.147, "usdollar": 0.172, "oil": 0.13}},
    {"id": "eq20", "name": "Equities fall 20%", "kind": "hypothetical", "shocks": {"globalequities": -0.20}},
    {"id": "rates", "name": "Rates rise 100 bp (Treasuries -6%)", "kind": "hypothetical", "shocks": {"ustreasuries": -0.06}},
    {"id": "credit", "name": "Credit spreads widen (high yield -10%)", "kind": "hypothetical", "shocks": {"highyieldcredit": -0.10}},
    {"id": "usd", "name": "Dollar rises 10%", "kind": "hypothetical", "shocks": {"usdollar": 0.10}},
    {"id": "oil", "name": "Oil falls 30%", "kind": "hypothetical", "shocks": {"oil": -0.30}},
    {"id": "stag", "name": "Stagflation mix", "kind": "hypothetical",
     "shocks": {"globalequities": -0.15, "ustreasuries": -0.08, "highyieldcredit": -0.08, "usdollar": 0.05, "oil": 0.30}},
]


def _compound(x) -> float:
    return float(np.prod(1 + np.asarray(x, float)) - 1)


def resolve_scenario(sc: dict, factors: list[Series], SF: np.ndarray, propagate: bool = True) -> dict:
    """Factor moves for a scenario. Unspecified factors move with the specified ones in line with
    their history (conditional mean s_U = S_UK S_KK^-1 s_K) unless propagation is off."""
    keys = [norm(f.name) for f in factors]
    s: list[float | None] = [None] * len(keys)
    src = "preset"
    if sc["kind"] == "historical":
        ms = ym_range(sc["from"], sc["to"])
        if all(all(m in f.ret for m in ms) for f in factors):
            src = "data"
            s = [_compound([f.ret[m] for m in ms]) for f in factors]
        else:
            s = [sc["preset"].get(k) for k in keys]
    else:
        src = sc["kind"]
        s = [(sc.get("shocks") or {}).get(k) for k in keys]
    Kn = [i for i, v in enumerate(s) if v is not None]
    Un = [i for i, v in enumerate(s) if v is None]
    out = np.array([0.0 if v is None else float(v) for v in s])
    if Un and Kn and propagate and sc["kind"] != "historical":
        try:
            out[Un] = SF[np.ix_(Un, Kn)] @ np.linalg.solve(SF[np.ix_(Kn, Kn)], out[Kn])
        except np.linalg.LinAlgError:
            out[Un] = 0.0
    return {"shocks": out, "src": src, "specified": Kn}


def apply_shocks(B: np.ndarray, w: np.ndarray, sleeve_idx: np.ndarray, n_sleeves: int, s: np.ndarray, bench_beta) -> dict:
    hI = B @ s
    by_sleeve = np.zeros(n_sleeves)
    for i in range(len(w)):
        by_sleeve[sleeve_idx[i]] += w[i] * hI[i]
    return {"port": float(w @ hI), "bench": float(bench_beta @ s) if bench_beta is not None else None, "by_sleeve": by_sleeve, "holding": hI}


def reverse_stress(port_beta: np.ndarray, SF: np.ndarray, loss: float = 0.10) -> dict | None:
    """Most likely factor move (minimum Mahalanobis distance) producing a portfolio loss of `loss`:
    s* = -L * SF b / (b' SF b)."""
    Sb = SF @ port_beta
    q = float(port_beta @ Sb)
    if q <= 1e-16:
        return None
    return {"loss": loss, "shocks": -loss * Sb / q, "sigma_m": loss / math.sqrt(q), "sigma_a": loss / math.sqrt(q * 12)}
