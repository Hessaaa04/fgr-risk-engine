"""Turn a SyntheticPortfolio into (a) a riskcore Dataset and (b) the v0.4.2 engine's dataset format.

(b) exists only for the parity test that runs the frozen v0.4.2 JavaScript engine
on the same synthetic data and compares its answers with riskcore's.
"""

from __future__ import annotations

import math

from riskcore.calendar import month_end
from riskcore.data import Dataset, Holding, Observation, Series, norm

from .generator import SLEEVES, SyntheticPortfolio


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def to_dataset(p: SyntheticPortfolio) -> Dataset:
    inst = p.instruments.set_index("instrument")
    holdings = {n: Holding(n, inst.loc[n, "sleeve"], bool(inst.loc[n, "liquid"]), valuation_frequency=str(inst.loc[n, "valuation_frequency"])) for n in inst.index}
    v = p.valuations
    for name, month, value, ret in zip(v["instrument"], v["month"], v["value"], v["return"]):
        holdings[name].data[month] = Observation(_num(value), _num(ret))
    has_ret = {m: bool(p.valuations.loc[p.valuations.month == m, "return"].notna().any()) for m in p.months}
    series = {}
    for r in p.market_meta.itertuples(index=False):
        col = p.market[r.name]
        series[norm(r.name)] = Series(r.name, r.type, r.ticker, {m: float(v) for m, v in col.items()})
    return Dataset(list(holdings.values()), list(SLEEVES), list(p.months), has_ret, series)


def to_legacy(ds: Dataset) -> dict:
    """The JSON shape RE.analyse() in legacy/v0_4_2/engine.js expects (as built by RE.buildDataset)."""
    holdings = []
    for h in ds.holdings:
        holdings.append({"name": h.name, "sleeve": h.sleeve, "liquid": h.liquid,
                         "data": {m: {"val": o.val, "ret": o.ret, "w": None, "err": None} for m, o in h.data.items()}})
    return {
        "demo": False,
        "months": ds.months,
        "monthInfo": {m: {"hasReturn": ds.has_return[m], "date": month_end(m)} for m in ds.months},
        "holdings": holdings,
        "sleeves": [{"name": s, "data": {}} for s in ds.sleeves],
        "total": {"data": {}},
        "series": {k: {"name": s.name, "type": s.type, "ticker": s.ticker, "ret": s.ret, "lvl": s.lvl} for k, s in ds.series.items()},
        "issues": [],
        "benchmarkNote": "",
    }
