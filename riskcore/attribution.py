"""Brinson-Fachler attribution by sleeve, linked over months with Carino factors. Ported from v0.4.2.

Allocation_i = (wp_i - wb_i)(Rb_i - Rb); Selection_i = wb_i (Rp_i - Rb_i) + interaction.
Interaction is counted inside selection. A sleeve with no benchmark index uses its
own return as its benchmark return, so its whole effect is allocation.
"""

from __future__ import annotations

import math

import numpy as np

from .calendar import ym_add
from .data import Dataset, Series, norm


def carino_k(a: float, b: float) -> float:
    return 1 / (1 + a) if abs(a - b) < 1e-12 else (math.log(1 + a) - math.log(1 + b)) / (a - b)


def _compound(x) -> float:
    return float(np.prod(1 + np.asarray(x, float)) - 1)


def brinson(ds: Dataset, months: list[str], policy: dict[str, tuple[float, Series | None]]) -> dict:
    """policy: sleeve -> (benchmark weight, benchmark index or None). Weights are normalised to 1."""
    SL = ds.sleeves
    wsum = sum(policy.get(s, (0.0, None))[0] for s in SL)
    pol = [(policy.get(s, (0.0, None))[0] / wsum if wsum > 0 else 0.0, policy.get(s, (0.0, None))[1]) for s in SL]
    rows, RpT, RbT = [], [], []
    for m in months:
        prev = ym_add(m, -1)
        starts = [(h, h.data[prev].val) for h in ds.holdings if prev in h.data and (h.data[prev].val or 0) > 0]
        tv = sum(v for _, v in starts)
        wp = np.array([sum(v for h, v in starts if norm(h.sleeve) == norm(s)) / tv if tv > 0 else 0.0 for s in SL])
        rps = []
        for s in SL:
            rep = ds.sleeve_returns.get(s, {}).get(m)
            if rep is not None:
                rps.append(rep)
                continue
            a = b = 0.0
            for h, v in starts:
                d = h.data.get(m)
                if norm(h.sleeve) == norm(s) and d is not None and d.ret is not None:
                    a += v * d.ret
                    b += v
            rps.append(a / b if b > 0 else 0.0)
        rps = np.array(rps)
        rbs = [ser.ret.get(m) if ser is not None else None for _, ser in pol]
        Rb = sum(wb * rbs[s] for s, (wb, _) in enumerate(pol) if wb > 0)
        rb = np.array([rps[s] if rbs[s] is None else rbs[s] for s in range(len(SL))])
        wb = np.array([p[0] for p in pol])
        alloc = (wp - wb) * (rb - Rb)
        sel = wb * (rps - rb) + (wp - wb) * (rps - rb)
        rows.append((alloc, sel))
        RpT.append(float(wp @ rps))
        RbT.append(float(Rb))
    Rp, Rb = _compound(RpT), _compound(RbT)
    k = carino_k(Rp, Rb)
    A = np.zeros(len(SL))
    S = np.zeros(len(SL))
    for t, (a, s) in enumerate(rows):
        kt = carino_k(RpT[t], RbT[t]) / k
        A += a * kt
        S += s * kt
    return {"Rp": Rp, "Rb": Rb, "excess": Rp - Rb, "alloc": A, "sel": S, "sleeves": SL}
