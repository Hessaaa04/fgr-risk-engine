"""One call that runs the ported v0.4.2 analysis on a dataset, plus v2 data-quality labels."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import illiquid
from .active import active_risk
from .calendar import ym_range
from .data import Dataset, norm
from .estimation import Lineage, build_estimation_input, complete_months, lineage_share, portfolio_return
from .factors import factor_exposures, pca
from .risk import analyse_risk, liquidity
from .stress import SCENARIOS, apply_shocks, factor_roles, resolve_scenario, reverse_stress
from .uncertainty import confidence_label


@dataclass
class Settings:
    today: str
    as_of: str | None = None
    window: int = 60
    min_coverage: float = 0.4
    conf: float = 0.95
    risk_benchmark: str | None = None
    perf_benchmark: str | None = None
    proxies: dict[str, str] = field(default_factory=dict)
    liquidity_overrides: dict[str, bool] = field(default_factory=dict)
    liq_target: float = 0.90
    reverse_loss: float = 0.10
    propagate: bool = True
    custom_shocks: dict[str, float] = field(default_factory=dict)
    factor_map: dict[str, str] = field(default_factory=dict)  # factor name -> scenario role (V-04)
    desmooth: bool = True  # correct smoothed and quarterly-valued holdings (V-01, V-03); False reproduces v0.4.2
    assumed_betas: dict[str, float] = field(default_factory=dict)  # analyst equity beta for holdings valued yearly


def _compound(xs) -> float:
    p = 1.0
    for x in xs:
        p *= 1 + x
    return p - 1


def analyse(ds: Dataset, st: Settings) -> dict:
    complete = complete_months(ds, st.today)
    if not complete:
        raise ValueError("No complete month was found.")
    as_of = st.as_of if st.as_of in complete else complete[-1]
    for h in ds.holdings:
        if h.name in st.liquidity_overrides:
            h.liquid = st.liquidity_overrides[h.name]
    inp = build_estimation_input(ds, as_of, st.window, st.min_coverage, st.proxies)
    factors = ds.series_of("factor")
    roles = factor_roles(factors, st.factor_map)
    if st.desmooth:
        illiquid.apply(ds, inp, factors, roles, st.assumed_betas)
    if len(inp.months) < 3:
        raise ValueError(f"Fewer than three months of usable returns up to {as_of}.")
    R = analyse_risk(inp, st.conf)

    risk_bm = ds.find_series(st.risk_benchmark)
    perf_bm = ds.find_series(st.perf_benchmark)
    out: dict = {
        "as_of": as_of,
        "complete_months": complete,
        "months": inp.months,
        "T": len(inp.months),
        "N": len(inp.positions),
        "aum": inp.aum,
        "w": inp.w,
        "X": inp.X,
        "risk": R,
        "liquidity": liquidity(R.holdings, st.liq_target),
        "active_risk": active_risk(R.rp, inp.months, risk_bm, R.z),
        "active_perf": active_risk(R.rp, inp.months, perf_bm, R.z),
    }

    # data quality (v2): lineage shares and a plain confidence label
    shares = lineage_share(inp)
    own = shares[Lineage.REPORTED.value]
    out["lineage"] = shares
    stale_w = sum(h["w"] for h in R.holdings if h["stale"])
    out["stale_weight"] = stale_w
    modelled = shares[Lineage.PROXY.value] + shares[Lineage.DESMOOTHED.value] + shares[Lineage.FACTOR_MODEL.value]
    out["confidence_label"] = confidence_label(len(inp.months), own, modelled, stale_w)
    out["adjustments"] = inp.adjustments

    # realised year to date
    yr = as_of[:4]
    ms = [m for m in complete if yr + "-01" <= m <= as_of]
    rs = [portfolio_return(ds, m) for m in ms]
    out["ytd"] = None if any(r is None for r in rs) else _compound(rs)

    F = factor_exposures(inp.X, inp.w, R.rp, inp.months, factors, risk_bm, inp.sleeve_idx, R.sleeve_w)
    out["factors"] = F
    out["pca"] = pca(R.C, inp.w)
    out["stress"] = None
    out["reverse"] = None
    if F is not None:
        scen = list(SCENARIOS)
        if any(v is not None for v in st.custom_shocks.values()):
            scen.append({"id": "custom", "name": "Custom scenario", "kind": "custom", "shocks": st.custom_shocks})
        out["factor_roles"] = dict(zip([f.name for f in factors], roles))
        res = []
        for sc in scen:
            r = resolve_scenario(sc, factors, F["SF"], st.propagate, roles)
            if r["unmapped"]:  # never show a silent 0% (V-04)
                res.append({"id": sc["id"], "src": r["src"], "shocks": r["shocks"], "port": None, "bench": None, "actual": None,
                            "error": "No loaded factor is mapped to: " + ", ".join(r["unmapped"]) + "."})
                continue
            a = apply_shocks(F["B"], inp.w, inp.sleeve_idx, len(inp.sleeves), r["shocks"], F["bench"])
            actual = None
            if sc["kind"] == "historical":
                mm = ym_range(sc["from"], sc["to"])
                rr = [portfolio_return(ds, m) if m in complete else None for m in mm]
                actual = None if any(x is None for x in rr) else _compound(rr)
            res.append({"id": sc["id"], "src": r["src"], "shocks": r["shocks"], "port": a["port"], "bench": a["bench"], "actual": actual})
        out["stress"] = res
        out["reverse"] = reverse_stress(F["port"], F["SF"], st.reverse_loss)
    return out


__all__ = ["Settings", "analyse", "norm"]
