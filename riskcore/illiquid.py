"""Corrections for holdings whose reported returns understate their risk (new in v2; validation V-01, V-03).

Two cases, applied to the estimation matrix before any risk figure is computed:

1. Monthly-valued but smoothed (hedge funds, some property funds). If the first-order
   autocorrelation of the holding's latest unbroken run of monthly returns (36+ months,
   whole history, not just the window: V-12) is above PHI_MIN and above 2/sqrt(n) (clearly not
   sampling noise), and the holding is not cash-like, its returns in the window are
   desmoothed with Geltner: r*_t = (r_t - phi r_{t-1}) / (1 - phi). Lineage DESMOOTHED.

2. Valued quarterly (private equity, many property funds). Returns are compounded into the
   fund's own quarters and regressed on the global equity factor for the same quarter and the
   quarter before (Dimson, lags summed), because appraisal-based values react late. The window's
   monthly cells are replaced by alpha/3 + beta x equity_t, and the residual variance (per month)
   is added to the covariance diagonal. Lineage FACTOR_MODEL. Needs 12+ quarters.
   Only equities are used: 40 quarters cannot support five factors (validator's parsimony rule).

Valued yearly: about ten data points cannot support any estimate, so nothing is fitted. An
analyst-supplied equity beta (`assumed_betas`) is used if given, shown as an assumption; otherwise
the holding keeps its reported returns and is flagged 'needs an assumed beta or proxy'.

Everything here is an estimate with real uncertainty; every change is listed in inp.adjustments
and every changed cell carries its lineage so the confidence label can count it.
"""

from __future__ import annotations

import math
import re

import numpy as np

from .calendar import ym_add
from .data import Dataset, Series
from .estimation import EstimationInput, Lineage, own_history
from .smoothing import PHI_CAP, ar1

PHI_MIN = 0.10  # below this, smoothing is too small to correct
MIN_VOL_A = 0.01  # cash-like holdings (under 1% a year) are autocorrelated through interest rates, not appraisal smoothing
MIN_RUN = 36  # months of unbroken monthly history to estimate phi
MIN_QUARTERS = 12


def _last_run(ms: list[str]) -> list[str]:
    out: list[str] = []
    for m in ms:
        out = out + [m] if out and ym_add(out[-1], 1) == m else [m]
    return out


def equity_factor(factors: list[Series], roles: list[str | None] | None = None) -> Series | None:
    if roles:
        for f, r in zip(factors, roles):
            if r == "globalequities":
                return f
    return next((f for f in factors if re.search("equit", f.name, re.I)), None)


def _compound(x) -> float:
    return float(np.prod(1 + np.asarray(x, float)) - 1)


def quarterly_dimson(hist: dict[str, float], eq: Series) -> dict | None:
    """Regress the fund's quarterly returns on equity returns this quarter and last quarter.
    Quarters are aligned to the fund's own revaluation months (the most common month-of-quarter)."""
    ms = sorted(hist)
    nz = [int(m[5:7]) % 3 for m in ms if abs(hist[m]) >= 0.0005]
    if not nz:
        return None
    phase = max(range(3), key=nz.count)
    ends = [m for m in ms if int(m[5:7]) % 3 == phase]
    rows = []
    for e in ends:
        q = [ym_add(e, -2), ym_add(e, -1), e]
        lag = [ym_add(e, -5), ym_add(e, -4), ym_add(e, -3)]
        if all(m in hist for m in q) and all(m in eq.ret for m in q + lag):
            rows.append((_compound([hist[m] for m in q]), _compound([eq.ret[m] for m in q]), _compound([eq.ret[m] for m in lag])))
    if len(rows) < MIN_QUARTERS:
        return None
    y = np.array([r[0] for r in rows])
    Fm = np.column_stack([np.ones(len(rows)), [r[1] for r in rows], [r[2] for r in rows]])
    coef, *_ = np.linalg.lstsq(Fm, y, rcond=None)
    res = y - Fm @ coef
    dof = max(len(rows) - 3, 1)
    return {"alpha_q": float(coef[0]), "beta": float(coef[1] + coef[2]), "beta_0": float(coef[1]), "beta_1": float(coef[2]),
            "resid_var_q": float(res @ res / dof), "n": len(rows)}


def apply(ds: Dataset, inp: EstimationInput, factors: list[Series], roles: list[str | None] | None = None,
          assumed_betas: dict[str, float] | None = None) -> EstimationInput:
    """Correct the estimation matrix in place for smoothed and infrequently valued holdings; returns inp."""
    assumed_betas = assumed_betas or {}
    eq = equity_factor(factors, roles)
    X = inp.X.copy()
    T, N = X.shape
    extra = np.zeros(N)
    adj: list[dict] = []
    for i, h in enumerate(inp.positions):
        freq = inp.freq[i] if inp.freq else "unknown"
        hist = own_history(ds, h, inp.as_of)
        own_rows = [t for t in range(T) if inp.lineage[t][i] == Lineage.REPORTED]
        if not own_rows:
            continue
        if freq == "monthly":
            run = _last_run(sorted(hist))
            if len(run) < MIN_RUN:
                continue
            rr = np.array([hist[m] for m in run])
            phi_raw = ar1(rr)
            # must be clearly above sampling noise (about 2 standard errors, 2/sqrt(n)) as well as PHI_MIN
            if phi_raw <= max(PHI_MIN, 2 / math.sqrt(len(rr))) or float(rr.std(ddof=1)) * math.sqrt(12) < MIN_VOL_A:
                continue
            phi = min(phi_raw, PHI_CAP)
            for t in own_rows:
                m, prev = inp.months[t], ym_add(inp.months[t], -1)
                if prev in hist:
                    X[t, i] = (hist[m] - phi * hist[prev]) / (1 - phi)
                    inp.lineage[t][i] = Lineage.DESMOOTHED
            adj.append({"name": h.name, "freq": freq, "method": "desmoothed", "phi": phi, "phi_capped": phi_raw > PHI_CAP, "n": len(run)})
        elif freq in ("quarterly", "annual"):
            fit = None
            if h.name in assumed_betas and eq is not None:
                fit = {"alpha_q": 0.0, "beta": float(assumed_betas[h.name]), "resid_var_q": None, "n": 0}
                method = "assumed beta"
            elif freq == "quarterly" and eq is not None:
                fit = quarterly_dimson(hist, eq)
                method = "factor model"
            if fit is None:
                adj.append({"name": h.name, "freq": freq, "method": "needs an assumed beta or proxy", "n": len(hist)})
                continue
            if fit["resid_var_q"] is None:  # assumed beta: keep the fund's own variance beyond the equity part
                r = np.array([hist[m] for m in sorted(hist)])
                tot_m = float(np.var(r, ddof=1)) if len(r) > 2 else 0.0  # lumpy monthly series: about the period variance / months per period
                eqv = float(np.var([eq.ret[m] for m in inp.months if m in eq.ret], ddof=1))
                resid_m = max(tot_m - fit["beta"] ** 2 * eqv, 0.0)
            else:
                resid_m = fit["resid_var_q"] / 3
            for t in own_rows:
                m = inp.months[t]
                if m in eq.ret:
                    X[t, i] = fit["alpha_q"] / 3 + fit["beta"] * eq.ret[m]
                    inp.lineage[t][i] = Lineage.FACTOR_MODEL
            extra[i] = resid_m
            adj.append({"name": h.name, "freq": freq, "method": method, "beta": fit["beta"], "n": fit["n"],
                        "resid_vol_a": math.sqrt(resid_m * 12)})
    inp.X_raw = inp.X
    inp.X = X
    inp.extra_var = extra if extra.any() else None
    inp.adjustments = adj
    return inp
