"""Which months count, and the return matrix used for risk estimation.

Ported from v0.4.2 (engine.js: completeMonths, portReturn, analyse 'estimation
window' and 'return history' steps). One deliberate addition: every cell of the
matrix carries its lineage, so a risk figure can say how much of it rests on
filled-in rather than reported returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from .calendar import month_open, ym_add, ym_range
from .data import Dataset, Holding, norm
from .smoothing import observed_frequency

MAX_MISSING_SHARE = 0.02  # a month counts only if <= 2% of value lacks a return


class Lineage(StrEnum):
    REPORTED = "reported"  # the holding's own return
    PROXY = "proxy"  # a stand-in index chosen for this holding
    PEER_FILL = "peer_fill"  # value-weighted return of current holdings in the same sleeve
    PAST_SLEEVE_FILL = "past_sleeve_fill"  # what the fund's holdings in that sleeve earned at the time
    ZERO_FILL = "zero_fill"  # nothing available: set to 0 (flagged as no data)
    DESMOOTHED = "desmoothed"  # the holding's own return with appraisal smoothing removed (Geltner)
    FACTOR_MODEL = "factor_model"  # modelled from market factors because the holding is valued quarterly or yearly


def complete_months(ds: Dataset, today: str) -> list[str]:
    """Months that have ended and where at most 2% of last month's value lacks a return."""
    out = []
    for i, ym in enumerate(ds.months):
        if not ds.has_return.get(ym) or month_open(ym, today):
            continue
        prev = ds.months[i - 1] if i > 0 else None
        tot = miss = 0.0
        for h in ds.holdings:
            p = h.data.get(prev).val if prev and prev in h.data else None
            if p is not None and p > 0:
                tot += p
                c = h.data.get(ym)
                if c is None or c.val is None or c.ret is None:
                    miss += p
        if tot > 0 and miss / tot <= MAX_MISSING_SHARE:
            out.append(ym)
    return out


def portfolio_return(ds: Dataset, ym: str) -> float | None:
    """Value-weighted return of all holdings, weighted by start-of-month value."""
    prev = ym_add(ym, -1)
    starts = [(h, h.data[prev].val) for h in ds.holdings if prev in h.data and (h.data[prev].val or 0) > 0]
    tv = sum(v for _, v in starts)
    if not tv > 0:
        return None
    c = miss = 0.0
    for h, v in starts:
        d = h.data.get(ym)
        if d is not None and d.ret is not None:
            c += v / tv * d.ret
        else:
            miss += v
    return None if miss / tv > MAX_MISSING_SHARE else c


@dataclass
class EstimationInput:
    as_of: str
    positions: list[Holding]
    values: np.ndarray  # value per position at as_of
    w: np.ndarray  # weights at as_of
    sleeves: list[str]  # sleeves that hold positions, in dataset order
    sleeve_idx: np.ndarray  # sleeve index per position
    months: list[str]  # estimation window
    X: np.ndarray  # T x N monthly returns
    lineage: list[list[Lineage]]  # T x N
    coverage: dict[str, float]  # share of weight with own (or proxy) data, per candidate month
    freq: list[str] = field(default_factory=list)  # valuation frequency per position: recorded, else observed
    X_raw: np.ndarray | None = None  # the matrix before any illiquid adjustment (None = not adjusted)
    extra_var: np.ndarray | None = None  # monthly idiosyncratic variance added for factor-modelled holdings
    adjustments: list[dict] = field(default_factory=list)  # what was changed, per holding, for display

    @property
    def aum(self) -> float:
        return float(self.values.sum())


def own_history(ds: Dataset, h: Holding, as_of: str) -> dict[str, float]:
    """A holding's own monthly returns up to as_of (from a matching history series and from the dataset)."""
    m: dict[str, float] = {}
    s = ds.find_series(h.name)
    if s is not None:
        m.update({k: v for k, v in s.ret.items() if k <= as_of})
    for i, ym in enumerate(ds.months):
        if ym > as_of or not ds.has_return.get(ym):
            continue
        d = h.data.get(ym)
        p = h.data[ds.months[i - 1]].val if i > 0 and ds.months[i - 1] in h.data else None
        if d is not None and d.ret is not None and ((d.val or 0) > 0 or (p or 0) > 0):
            m[ym] = d.ret
    return m


def build_estimation_input(
    ds: Dataset,
    as_of: str,
    window: int = 60,
    min_coverage: float = 0.4,
    proxies: dict[str, str] | None = None,
) -> EstimationInput:
    proxies = proxies or {}
    pos = [h for h in ds.holdings if as_of in h.data and (h.data[as_of].val or 0) > 0]
    if not pos:
        raise ValueError(f"No holdings with a value at {as_of}.")
    values = np.array([h.data[as_of].val for h in pos], float)
    w = values / values.sum()
    n = len(pos)
    sleeves = [s for s in ds.sleeves if any(norm(h.sleeve) == norm(s) for h in pos)]
    skeys = [norm(s) for s in sleeves]
    sidx = np.array([skeys.index(norm(h.sleeve)) for h in pos])

    hist = [own_history(ds, h, as_of) for h in pos]
    proxy = []
    for h in pos:
        p = ds.find_series(proxies.get(h.name)) if proxies.get(h.name) else None
        proxy.append(p.ret if p is not None else None)

    def own_at(i: int, ym: str) -> float | None:
        if proxy[i] is not None and ym in proxy[i]:
            return proxy[i][ym]
        return hist[i].get(ym)

    W = max(3, min(240, window or 60))
    cand = ym_range(ym_add(as_of, -(W - 1)), as_of)
    months: list[str] = []
    coverage: dict[str, float] = {}
    for ym in reversed(cand):
        cov = float(sum(w[i] for i in range(n) if own_at(i, ym) is not None))
        coverage[ym] = cov
        if cov < (min_coverage or 0.4):
            break
        months.insert(0, ym)

    T = len(months)
    X = np.zeros((T, n))
    lin: list[list[Lineage]] = []
    for t, ym in enumerate(months):
        row = [Lineage.ZERO_FILL] * n
        s_sum = np.zeros(len(sleeves))
        s_w = np.zeros(len(sleeves))
        for i in range(n):
            v = own_at(i, ym)
            if v is not None:
                X[t, i] = v
                row[i] = Lineage.PROXY if proxy[i] is not None and ym in proxy[i] else Lineage.REPORTED
                s_sum[sidx[i]] += w[i] * v
                s_w[sidx[i]] += w[i]
        past: dict[int, float | None] = {}
        for i in range(n):
            if own_at(i, ym) is not None:
                continue
            s = int(sidx[i])
            if s_w[s] > 0:
                X[t, i] = s_sum[s] / s_w[s]
                row[i] = Lineage.PEER_FILL
            else:
                if s not in past:
                    past[s] = _past_sleeve(ds, skeys[s], ym)
                if past[s] is None:
                    X[t, i] = 0.0
                    row[i] = Lineage.ZERO_FILL
                else:
                    X[t, i] = past[s]
                    row[i] = Lineage.PAST_SLEEVE_FILL
        lin.append(row)

    freq = [h.valuation_frequency or observed_frequency(hist[i]) for i, h in enumerate(pos)]
    return EstimationInput(as_of, pos, values, w, sleeves, sidx, months, X, lin, coverage, freq)


def _past_sleeve(ds: Dataset, skey: str, ym: str) -> float | None:
    prev = ym_add(ym, -1)
    a = b = 0.0
    for h in ds.holdings:
        if norm(h.sleeve) != skey:
            continue
        p, d = h.data.get(prev), h.data.get(ym)
        if p is not None and (p.val or 0) > 0 and d is not None and d.ret is not None:
            a += p.val * d.ret
            b += p.val
    return a / b if b > 0 else None


def lineage_share(inp: EstimationInput) -> dict[str, float]:
    """Weight-averaged share of matrix cells by lineage (sums to 1)."""
    T = len(inp.months)
    out = {k.value: 0.0 for k in Lineage}
    if T == 0:
        return out
    for row in inp.lineage:
        for i, lab in enumerate(row):
            out[lab.value] += float(inp.w[i]) / T
    return out
