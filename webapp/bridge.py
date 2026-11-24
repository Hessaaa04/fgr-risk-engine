"""Glue between the website and riskcore (runs in the browser through Pyodide, and in tests).

The page reads Excel files itself (the v0.4.2 reader) and passes the dataset here as
JSON in the v0.4.2 shape. Everything returned is plain JSON for the page to draw.
No file, network or database access: data stays in the browser that loaded it.
Numbers come from riskcore; this module only selects, labels and packages them.
"""

from __future__ import annotations

import json
import math
import re

import numpy as np

from riskcore import illiquid
from riskcore import liquidity_profile as lp
from riskcore.analyse import Settings, analyse
from riskcore.attribution import brinson
from riskcore.calendar import ym_add
from riskcore.data import Dataset, Holding, Observation, Series, norm
from riskcore.estimation import build_estimation_input, complete_months, own_history, portfolio_return
from riskcore.performance import compare, cumulative, rolling_vol, series_stats
from riskcore.risk import analyse_risk
from riskcore.smoothing import MIN_MONTHS as DESMOOTH_MIN
from riskcore.smoothing import ar1, geltner, observed_frequency
from riskcore.stress import SCENARIOS, apply_shocks, factor_roles, resolve_scenario, reverse_stress
from riskcore.uncertainty import bootstrap_interval, vol_standard_error

from .liquidity_reader import read_report

STATE: dict = {}


# ---------------------------------------------------------------- loading
def from_legacy(j: dict) -> Dataset:
    """Dataset from the v0.4.2 JSON shape (RE.buildDataset). Missing stays None."""
    holdings = []
    for h in j["holdings"]:
        data = {m: Observation(_n(d.get("val")), _n(d.get("ret"))) for m, d in h["data"].items()}
        holdings.append(Holding(h["name"], h["sleeve"], bool(h["liquid"]) if h.get("liquid") is not None else True, data))
    months = list(j["months"])
    has_ret = {m: bool(j["monthInfo"].get(m, {}).get("hasReturn")) for m in months}
    series = {}
    for k, s in (j.get("series") or {}).items():
        series[k] = Series(s["name"], s.get("type") or "holding", s.get("ticker") or "",
                           {m: float(v) for m, v in (s.get("ret") or {}).items() if v is not None},
                           {m: float(v) for m, v in (s.get("lvl") or {}).items() if v is not None})
    sleeve_ret = {s["name"]: {m: _n(d.get("ret")) for m, d in (s.get("data") or {}).items()} for s in j["sleeves"]}
    total = {m: _n(d.get("ret")) for m, d in ((j.get("total") or {}).get("data") or {}).items()}
    return Dataset(holdings, [s["name"] for s in j["sleeves"]], months, has_ret, series, sleeve_ret, total)


def _n(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def load(ds_json: str, today: str) -> str:
    j = json.loads(ds_json)
    ds = from_legacy(j)
    STATE.clear()
    STATE.update(ds=ds, raw=j, today=today)
    comp = complete_months(ds, today)
    return _dump({
        "holdings": len(ds.holdings), "sleeves": ds.sleeves, "months": ds.months, "complete": comp,
        "series": [{"name": s.name, "type": s.type, "ticker": s.ticker, "n": len(s.ret), "from": min(s.ret) if s.ret else None,
                    "to": max(s.ret) if s.ret else None} for s in ds.series.values()],
        "defaults": _default_benchmarks(ds),
        "names": [h.name for h in ds.holdings],
    })


def _default_benchmarks(ds: Dataset) -> dict:
    """Same choice as v0.4.2: a 50/50 reference for risk, Russell Multi-Asset 35 for performance."""
    bs = ds.series_of("benchmark")

    def pick(rx, nth):
        hit = next((b for b in bs if re.search(rx, b.name, re.I) or re.search(rx, b.ticker, re.I)), None)
        return hit or (bs[nth] if len(bs) > nth else None)

    r = pick(r"50\s*/?\s*50|bmadm55", 0)
    p = pick(r"russell|multi-?asset\s*35", 1)
    if p is r:
        p = next((b for b in bs if b is not r), None)
    return {"risk": r.name if r else None, "perf": p.name if p else None}


# ---------------------------------------------------------------- main run
def run(settings_json: str) -> str:
    ds: Dataset = STATE["ds"]
    s = json.loads(settings_json)
    d = _default_benchmarks(ds)
    st = Settings(
        today=STATE["today"], as_of=s.get("as_of"), window=int(s.get("window") or 36), conf=float(s.get("conf") or 0.95),
        risk_benchmark=s.get("risk_benchmark") or d["risk"], perf_benchmark=s.get("perf_benchmark") or d["perf"],
        desmooth=s.get("desmooth", True), assumed_betas=s.get("assumed_betas") or {},
        proxies=s.get("proxies") or {}, factor_map=s.get("factor_map") or {}, liquidity_overrides=s.get("liquidity") or {}, liq_target=float(s.get("liq_target") or 0.9),
        reverse_loss=float(s.get("reverse_loss") or 0.10), propagate=s.get("propagate", True),
    )
    # liquidity overrides change Holding objects; start from the loaded flags each run
    for h, raw in zip(ds.holdings, STATE["raw"]["holdings"]):
        h.liquid = bool(raw["liquid"]) if raw.get("liquid") is not None else True
    P = analyse(ds, st)
    R = P["risk"]
    STATE.update(P=P, st=st)
    T = P["T"]
    conf = st.conf
    rp = R.rp
    vol_rng = bootstrap_interval(rp, lambda x: float(x.std(ddof=1)) * math.sqrt(12)) if T >= 12 else (None, None)
    var_rng = bootstrap_interval(rp, lambda x: -float(np.quantile(x, 1 - conf))) if T >= 24 else (None, None)
    perf = _performance(ds, P["complete_months"], P["as_of"], st)
    out = {
        "as_of": P["as_of"], "months": P["months"], "T": T, "N": P["N"], "aum": P["aum"], "complete": P["complete_months"],
        "window": st.window, "conf": conf, "risk_benchmark": st.risk_benchmark, "perf_benchmark": st.perf_benchmark,
        "headline": {
            "vol": R.vol_a, "vol_range": list(vol_rng), "vol_se": vol_standard_error(R.vol_a, T),
            "var": R.var, "es": R.es, "hvar": R.hist_var, "hes": R.hist_es, "hvar_range": list(var_rng),
            "max_dd": R.max_dd, "ytd": P["ytd"], "z": R.z,
        },
        "quality": {"label": P["confidence_label"], "lineage": P["lineage"], "stale_weight": P["stale_weight"],
                    "reasons": _label_reasons(T, P["lineage"], P["stale_weight"])},
        "liquidity": P["liquidity"],
        "active_risk": _clean(P["active_risk"]), "active_perf": _clean(P["active_perf"]),
        "sleeves": [_clean(x) for x in R.sleeves],
        "holdings": [_clean({**h, "freq": observed_frequency(own_history(ds, _h(ds, h["name"]), P["as_of"]))}) for h in R.holdings],
        "rolling": _rolling(ds, P, st),
        "performance": perf,
        "factors": _factors(P),
        "factor_roles": P.get("factor_roles"),
        "adjustments": P.get("adjustments"),
        "stress": _stress_list(P),
        "reverse": _clean(P["reverse"]),
        "illiquid": _illiquid(ds, P),
        "attribution": _attribution(ds, P["complete_months"], P["as_of"], None, None, None),
    }
    return _dump(out)


def _h(ds, name):
    return next(h for h in ds.holdings if h.name == name)


def _label_reasons(T, lin, stale):
    own = lin.get("reported", 0)
    return [
        {"ok": T >= 60, "text": f"{T} months of history used (High needs 60 or more; under 36 is Low)."},
        {"ok": own >= 0.95, "text": f"{own:.1%} of the return history is the holdings' own reported data (High needs 95%; under 60% is Low)."},
        {"ok": _modelled(lin) == 0,
         "text": f"{_modelled(lin):.1%} is estimated: proxies, desmoothing or factor models for illiquid funds (High needs none; over 50% is Low)."},
        {"ok": stale <= 0.05, "text": f"{stale:.1%} of the portfolio has stale prices, which hide risk (High needs 5% or less; over 25% is Low)."},
    ]


def _modelled(lin):
    return lin.get("proxy", 0) + lin.get("desmoothed", 0) + lin.get("factor_model", 0)


def _rolling(ds, P, st):
    """Risk as the engine would have reported it at each past month-end (current method, that month's holdings),
    plus realised volatility of the portfolio's actual returns over the same trailing window."""
    comp = P["complete_months"]
    out = {"months": [], "vol": [], "var": [], "label_T": [], "realised": []}
    pr = {m: portfolio_return(ds, m) for m in comp}
    real = rolling_vol(pr, comp, st.window)
    for i, m in enumerate(comp):
        if m > P["as_of"]:
            break
        try:
            inp = build_estimation_input(ds, m, st.window, st.min_coverage, st.proxies)
        except ValueError:
            continue
        if st.desmooth:
            factors = ds.series_of("factor")
            illiquid.apply(ds, inp, factors, factor_roles(factors, st.factor_map), st.assumed_betas)
        if len(inp.months) < 12:
            continue
        R = analyse_risk(inp, st.conf)
        out["months"].append(m)
        out["vol"].append(R.vol_a)
        out["var"].append(R.var)
        out["label_T"].append(len(inp.months))
        out["realised"].append(real[i])
    return out


def _performance(ds, comp, as_of, st):
    months = [m for m in comp if m <= as_of]
    pr = {m: portfolio_return(ds, m) for m in months}
    bms = [s for s in ds.series.values() if s.type in ("benchmark", "index", "factor") and s.ret]
    return {
        "months": months,
        "port": [pr[m] for m in months],
        "series": [{"name": s.name, "type": s.type, "ret": [s.ret.get(m) for m in months]} for s in bms],
        "reported_total": [ds.total_returns.get(m) for m in months],
    }


def comparison(names_json: str, start: str, end: str) -> str:
    """Portfolio vs each chosen series over [start, end]."""
    ds: Dataset = STATE["ds"]
    P = STATE["P"]
    months = [m for m in P["complete_months"] if start <= m <= end]
    pr = {m: portfolio_return(ds, m) for m in months}
    chosen = [s for s in (ds.find_series(n) for n in json.loads(names_json)) if s is not None]
    # one common period for every row: months where the portfolio and every chosen series have a return
    common = [m for m in months if pr[m] is not None and all(m in s.ret for s in chosen)]
    dropped = [s.name for s in chosen if len([m for m in months if m in s.ret]) < 6]
    if dropped:  # a series that barely covers the period would shrink everyone's period; leave it out
        chosen = [s for s in chosen if s.name not in dropped]
        common = [m for m in months if pr[m] is not None and all(m in s.ret for s in chosen)]
    months = common
    rows = [{"name": s.name, "type": s.type, **_clean(compare(pr, s.ret, months))} for s in chosen]
    rows += [{"name": n, "n": 0, "dropped": True} for n in dropped]
    port_ms = [m for m in months if pr[m] is not None]
    return _dump({"months": months, "port": series_stats(np.array([pr[m] for m in port_ms])) if port_ms else None,
                  "cum_port": cumulative(pr, months),
                  "cum": {s.name: cumulative(s.ret, months) for s in chosen}, "rows": rows})


def _factors(P):
    F = P["factors"]
    if F is None:
        return None
    R = P["risk"]
    pc = P["pca"]
    return {
        "names": F["names"], "n": F["n"], "port": F["port"], "port_r2": F["port_r2"], "alpha_m": F["alpha_m"],
        "bench": F["bench"], "bench_r2": F["bench_r2"], "vol_a": F["vol_a"], "sleeve": F["sleeve"],
        "holdings": [{"name": h["name"], "sleeve": h["sleeve"], "w": h["w"], "beta": F["B"][i], "r2": F["r2"][i]} for i, h in enumerate(R.holdings)],
        "corr": _corr(F["SF"]),
        "pca": [{"share": c["share"], "port_share": c["port_share"],
                 "top": sorted(({"name": R.holdings[i]["name"], "load": float(c["vector"][k])} for k, i in enumerate(c["holdings"])),
                               key=lambda x: -abs(x["load"]))[:5]} for c in pc["comps"]] if pc else None,
    }


def _corr(S):
    d = np.sqrt(np.diag(S))
    return (S / np.outer(d, d)).tolist() if (d > 0).all() else None


def _stress_list(P):
    if P["stress"] is None:
        return None
    names = {s["id"]: s for s in SCENARIOS}
    out = []
    for s in P["stress"]:
        sc = names.get(s["id"], {})
        if s["port"] is None:
            out.append({"id": s["id"], "name": sc.get("name", s["id"]), "kind": sc.get("kind"), "from": sc.get("from"), "to": sc.get("to"),
                        "src": s["src"], "error": s.get("error"), "port": None, "bench": None, "actual": None, "by_sleeve": [], "loss_value": None,
                        "shocks": s["shocks"]})
            continue
        res = _apply(P, np.asarray(s["shocks"]))
        out.append({"id": s["id"], "name": sc.get("name", s["id"]), "kind": sc.get("kind"), "from": sc.get("from"), "to": sc.get("to"),
                    "src": s["src"], "shocks": s["shocks"], "port": s["port"], "bench": s["bench"], "actual": s["actual"],
                    "by_sleeve": res["by_sleeve"], "loss_value": s["port"] * P["aum"]})
    return out


def _apply(P, shocks):
    F = P["factors"]
    R = P["risk"]
    inp_w = np.array([h["w"] for h in R.holdings])
    sl = [x["name"] for x in R.sleeves]
    sidx = np.array([sl.index(h["sleeve"]) for h in R.holdings])
    a = apply_shocks(F["B"], inp_w, sidx, len(sl), shocks, F["bench"])
    return {"port": a["port"], "bench": a["bench"], "by_sleeve": [{"name": n, "impact": float(v)} for n, v in zip(sl, a["by_sleeve"])],
            "holdings": [{"name": h["name"], "sleeve": h["sleeve"], "w": h["w"], "shock": float(x), "impact": float(h["w"] * x)}
                         for h, x in zip(R.holdings, a["holding"])]}


def scenario(shocks_json: str, propagate: bool) -> str:
    """A user-built scenario: shocks keyed by factor name (decimal moves; missing = not specified)."""
    P = STATE["P"]
    F = P["factors"]
    if F is None:
        return _dump({"error": "No market factor history is loaded, so scenarios cannot be run."})
    given = json.loads(shocks_json)
    factors = STATE["ds"].series_of("factor")
    roles = factor_roles(factors, STATE["st"].factor_map)
    key = {f.name: (r or norm(f.name)) for f, r in zip(factors, roles)}
    sc = {"id": "custom", "kind": "custom", "shocks": {key.get(k, norm(k)): v for k, v in given.items() if v is not None}}
    r = resolve_scenario(sc, factors, F["SF"], bool(propagate), roles)
    res = _apply(P, r["shocks"])
    return _dump({"shocks": r["shocks"], "specified": r["specified"], **res, "loss_value": res["port"] * P["aum"],
                  "sigma": _mahalanobis(r["shocks"], F["SF"])})


def _mahalanobis(s, SF):
    try:
        return float(math.sqrt(max(float(s @ np.linalg.solve(SF, s)), 0.0)))
    except np.linalg.LinAlgError:
        return None


def reverse(loss: float) -> str:
    P = STATE["P"]
    F = P["factors"]
    if F is None:
        return _dump(None)
    r = reverse_stress(F["port"], F["SF"], float(loss))
    return _dump({**r, "names": F["names"]} if r else None)


def _illiquid(ds, P):
    """Smoothing check for holdings in illiquid sleeves or flagged illiquid."""
    eq = next((s for s in ds.series_of("factor") if re.search("equit", s.name, re.I)), None)
    rows = []
    for h in P["risk"].holdings:
        if h["liquid"] and not re.search("altern|strateg|private|property|real estate|hedge", h["sleeve"] + " " + h["name"], re.I):
            continue
        hist = own_history(ds, _h(ds, h["name"]), P["as_of"])
        ms = _last_run(sorted(hist))[-120:]  # consecutive months only: AR1 must not span gaps
        r = np.array([hist[m] for m in ms])
        freq = observed_frequency({m: hist[m] for m in ms})
        row = {"name": h["name"], "sleeve": h["sleeve"], "w": h["w"], "n": len(r), "freq": freq,
               "obs_vol": float(r.std(ddof=1)) * math.sqrt(12) if len(r) > 2 else None, "ar1": ar1(r) if len(r) > 2 else None,
               "eq_obs": None, "eq_desm": None, "desm_vol": None, "phi": None}
        if eq is not None:
            both = [m for m in ms if m in eq.ret]
            if len(both) > 12:
                row["eq_obs"] = float(np.corrcoef([hist[m] for m in both], [eq.ret[m] for m in both])[0, 1])
        if freq == "monthly" and len(r) >= DESMOOTH_MIN:
            dsm, phi = geltner(r)
            row.update(desm_vol=float(dsm.std(ddof=1)) * math.sqrt(12), phi=phi, status="desmoothed" if phi > 0.05 else "little smoothing")
            if eq is not None:
                both = [m for m in ms[1:] if m in eq.ret]
                if len(both) > 12:
                    dm = dict(zip(ms[1:], dsm))
                    row["eq_desm"] = float(np.corrcoef([dm[m] for m in both], [eq.ret[m] for m in both])[0, 1])
        elif freq in ("quarterly", "annual"):
            row["status"] = "needs a proxy index"
        else:
            row["status"] = "too little history"
        rows.append(row)
    return rows


def _last_run(ms: list[str]) -> list[str]:
    """The latest unbroken run of consecutive months."""
    out: list[str] = []
    for m in ms:
        out = out + [m] if out and ym_add(out[-1], 1) == m else [m]
    return out


def _attribution(ds, comp, as_of, start, end, policy):
    """Brinson-Fachler with Carino linking, plus holding contributions. policy: [{sleeve, weight, series}]."""
    avail = [m for m in comp if ym_add(m, -1) in ds.months and m <= as_of]
    start = start if start and start <= as_of else as_of[:4] + "-01"
    end = end if end and start <= end <= as_of else as_of
    months = [m for m in avail if start <= m <= end]
    is_default = policy is None
    if policy is None:
        policy = _default_policy(ds)
    out = {"from": start, "to": end, "available": avail, "months": months, "policy": policy, "is_default": is_default, "ok": False}
    if not months:
        out["reason"] = "No complete months in the selected period."
        return out
    # holding contributions (compounded within the period)
    contrib: dict[str, float] = {}
    cum = 1.0
    for m in months:
        prev = ym_add(m, -1)
        starts = [(h, h.data[prev].val) for h in ds.holdings if prev in h.data and (h.data[prev].val or 0) > 0]
        tv = sum(v for _, v in starts)
        c = 0.0
        for h, v in starts:
            d = h.data.get(m)
            if d is not None and d.ret is not None:
                x = v / tv * d.ret
                c += x
                contrib[h.name] = contrib.get(h.name, 0.0) + x * cum
        cum *= 1 + c
    out["contrib"] = sorted(({"name": k, "sleeve": _h(ds, k).sleeve, "c": v} for k, v in contrib.items()), key=lambda x: -x["c"])
    wsum = sum(float(p.get("weight") or 0) for p in policy)
    if wsum <= 0:
        out["reason"] = "Set the benchmark weights to run the attribution."
        return out
    pol = {p["sleeve"]: (float(p.get("weight") or 0), ds.find_series(p.get("series")) if p.get("series") else None) for p in policy}
    B = brinson(ds, months, pol)
    out["own_return_classes"] = B["own_return_classes"]
    out.update(ok=True, Rp=B["Rp"], Rb=B["Rb"], excess=B["excess"], alloc_total=float(np.sum(B["alloc"])), sel_total=float(np.sum(B["sel"])),
               sleeves=[{"name": s, "alloc": float(B["alloc"][i]), "sel": float(B["sel"][i]), "total": float(B["alloc"][i] + B["sel"][i]),
                         "wb": pol.get(s, (0, None))[0] / wsum, "series": pol[s][1].name if s in pol and pol[s][1] else ""}
                        for i, s in enumerate(B["sleeves"])])
    return out


def _default_policy(ds):
    eq = fi = None
    for s in ds.series_of("factor", "index"):
        if eq is None and (re.search("equit", s.name, re.I) or re.search("dmtr|acwi|nddu", s.ticker, re.I)):
            eq = s.name
        if fi is None and (re.search("bond|aggregate", s.name, re.I) or re.search("legatruu", s.ticker, re.I)):
            fi = s.name
    out = []
    for s in ds.sleeves:
        if re.search("equit", s, re.I) and eq:
            out.append({"sleeve": s, "weight": 35, "series": eq})
        elif re.search("fixed|bond", s, re.I) and fi:
            out.append({"sleeve": s, "weight": 65, "series": fi})
        else:
            out.append({"sleeve": s, "weight": 0, "series": ""})
    return out


def attribution(start: str, end: str, policy_json: str) -> str:
    P = STATE["P"]
    pol = json.loads(policy_json) if policy_json else None
    return _dump(_attribution(STATE["ds"], P["complete_months"], P["as_of"], start, end, pol))


# ---------------------------------------------------------------- liquidity report
def liquidity(files_json: str, settings_json: str) -> str:
    """files: [{name, sheets: {sheet: rows}}]. Settings: min_liquid, horizon, receivables, suspend, terms.
    Returns one analysed profile per month (oldest first) and the change between the last two."""
    files = json.loads(files_json)
    s = json.loads(settings_json or "{}")
    terms = {}
    for n, t in (s.get("terms") or {}).items():
        terms[n] = lp.Terms(gate=_n(t.get("gate")), lockup_end=t.get("lockup_end") or None, fee=_n(t.get("fee")))
    out, issues = [], []
    for f in files:
        try:
            pr, iss = read_report(f["sheets"], f.get("name", ""), bool(s.get("receivables")))
        except ValueError as e:
            issues.append({"level": "error", "text": f"Could not read {f.get('name', '')} as a liquidity report: {e}."})
            continue
        issues += iss
        a = lp.analyse(pr, float(s.get("min_liquid") or 0.90), int(s.get("horizon") or lp.LIQUID_MAX_DAYS), terms,
                       float(s.get("suspend") or 0.0))
        a["file"] = f.get("name", "")
        out.append(a)
    out.sort(key=lambda a: a["as_of"] or "")
    return _dump({"profiles": out, "issues": issues, "change": lp.compare(out[-2], out[-1]) if len(out) > 1 else None,
                  "buckets": [{"key": k, "name": n, "kind": kind} for k, n, kind in lp.BUCKETS]})


# ---------------------------------------------------------------- JSON
def _clean(x):
    if x is None:
        return None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return f if math.isfinite(f) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _dump(x) -> str:
    return json.dumps(_clean(x), separators=(",", ":"), default=str)
