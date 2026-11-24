"""riskcore must reproduce the frozen v0.4.2 engine on the same synthetic data.

The v0.4.2 JavaScript engine (legacy/v0_4_2/engine.js) was itself validated against an
independent numpy/scipy implementation. Here it is the oracle: each case runs it in Node
and compares every ported figure with riskcore's, within a stated tolerance.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from riskcore.analyse import Settings, analyse
from riskcore.attribution import brinson
from riskcore.estimation import complete_months
from synthetic import generate
from synthetic.adapters import to_dataset, to_legacy

HERE = Path(__file__).parent
TODAY = "2026-11-24"
RISK_BM = "50/50 reference (synthetic)"
PERF_BM = "Multi-asset 35 (synthetic)"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the v0.4.2 engine")

CASES = {
    "default": {},
    "conf99_window36": {"conf": 0.99, "window": 36},
    "as_of_2022_06": {"asOf": "2022-06", "window": 120},
    "proxy_and_overrides": {"proxy": {"Synthetic Property Fund A": "Global equities"}, "liq": {"Synthetic Hedge Fund A (Multi-Strategy)": False}},
    "custom_shock_no_propagation": {"custom": {"globalequities": -0.3, "oil": -0.4}, "propagate": False, "reverseLoss": 0.2},
    "custom_shock_propagated": {"custom": {"highyieldcredit": -0.12}},
}


def close(a, b, tol, what):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape, f"{what}: shape {a.shape} vs {b.shape}"
    d = float(np.max(np.abs(a - b))) if a.size else 0.0
    assert d <= tol, f"{what}: max difference {d:.3e} > {tol:.0e}"


@pytest.fixture(scope="module")
def portfolio():
    return generate()


def run_legacy(ds_json: dict, st: dict, tmp: Path) -> dict:
    (tmp / "ds.json").write_text(json.dumps(ds_json))
    (tmp / "st.json").write_text(json.dumps(st))
    subprocess.run(["node", str(HERE / "run_legacy.js"), str(tmp / "ds.json"), str(tmp / "st.json"), str(tmp / "out.json")], check=True)
    return json.loads((tmp / "out.json").read_text())


@pytest.mark.parametrize("case", list(CASES))
def test_matches_v042(case, portfolio, tmp_path):
    extra = CASES[case]
    st_js = {"today": TODAY, "riskBenchmark": RISK_BM, "perfBenchmark": PERF_BM, **extra}
    A = run_legacy(to_legacy(to_dataset(portfolio)), st_js, tmp_path)

    st = Settings(today=TODAY, as_of=extra.get("asOf"), window=extra.get("window", 60), conf=extra.get("conf", 0.95),
                  risk_benchmark=RISK_BM, perf_benchmark=PERF_BM, proxies=extra.get("proxy", {}),
                  liquidity_overrides=extra.get("liq", {}), reverse_loss=extra.get("reverseLoss", 0.10),
                  propagate=extra.get("propagate", True), custom_shocks=extra.get("custom", {}), desmooth=False)
    P = analyse(to_dataset(portfolio), st)
    R = P["risk"]

    assert P["as_of"] == A["asOf"] and P["months"] == A["months"]
    close(P["aum"], A["aum"], 1e-3, "AUM")
    close(P["w"], A["w"], 1e-12, "weights")
    close(P["X"], A["X"], 1e-12, "return matrix")
    close(R.C, A["C"], 1e-14, "covariance")
    close(R.vol_a, A["risk"]["volA"], 1e-12, "volatility")
    close(R.z, A["risk"]["z"], 1e-7, "normal quantile")
    close(R.var, A["risk"]["VaR"], 1e-8, "VaR")
    close(R.es, A["risk"]["CVaR"], 1e-8, "Expected Shortfall")
    if R.hist_var is not None:
        close(R.hist_var, A["risk"]["histVaR"], 1e-12, "historical VaR")
        close(R.hist_es, A["risk"]["histCVaR"], 1e-12, "historical ES")
    close(R.max_dd, A["risk"]["maxDD"], 1e-12, "max drawdown")
    for key, js in (("rc", "rc"), ("mvar", "mvar"), ("cvar", "cvar"), ("ivar", "ivar"), ("vol_a", "volA")):
        close([h[key] for h in R.holdings], [h[js] for h in A["holdings"]], 1e-8, f"holding {key}")
    assert [h["stale_v042"] for h in R.holdings] == [h["stale"] for h in A["holdings"]]  # v2 widens 'stale' (V-02, D21)
    assert [h["no_data"] for h in R.holdings] == [h["noData"] for h in A["holdings"]]
    close([s["w"] for s in R.sleeves], [s["w"] for s in A["sleeves"]], 1e-12, "sleeve weights")
    close([s["rc"] for s in R.sleeves], [s["rc"] for s in A["sleeves"]], 1e-10, "sleeve risk share")
    close([s["vol_a"] for s in R.sleeves], [s["volA"] for s in A["sleeves"]], 1e-12, "sleeve volatility")
    close(P["liquidity"]["liquid"], A["liquidity"]["liquid"], 1e-12, "liquidity")
    for mine, theirs in (("active_risk", "activeRisk"), ("active_perf", "activePerf")):
        for k, j in (("te", "te"), ("beta", "beta"), ("corr", "corr"), ("ir", "ir")):
            close(P[mine][k], A[theirs][j], 1e-10, f"{mine} {k}")
    if A["perf"]["ytd"]:
        close(P["ytd"], A["perf"]["ytd"]["port"], 1e-12, "YTD return")

    F, FA = P["factors"], A["factors"]
    close(F["B"], FA["B"], 1e-8, "factor betas")
    close(F["port"], FA["port"], 1e-8, "portfolio betas")
    close(F["port_r2"], FA["portR2"], 1e-8, "portfolio R2")
    close(F["SF"], FA["SF"], 1e-14, "factor covariance")
    close(F["bench"], FA["bench"], 1e-8, "benchmark betas")
    close([c["share"] for c in P["pca"]["comps"]], [c["share"] for c in A["pca"]["comps"]], 1e-8, "PCA variance share")
    close([c["port_share"] for c in P["pca"]["comps"]], [c["portShare"] for c in A["pca"]["comps"]], 1e-7, "PCA portfolio share")
    assert [s["id"] for s in P["stress"]] == [s["id"] for s in A["stress"]]
    close([s["shocks"] for s in P["stress"]], [s["shocks"] for s in A["stress"]], 1e-9, "stress factor moves")
    close([s["port"] for s in P["stress"]], [s["port"] for s in A["stress"]], 1e-9, "stress portfolio impact")
    close([s["bench"] for s in P["stress"]], [s["bench"] for s in A["stress"]], 1e-9, "stress benchmark impact")
    for p_, a_ in zip(P["stress"], A["stress"]):
        assert p_["src"] == a_["src"]
        assert (p_["actual"] is None) == (a_["actual"] is None)
        if p_["actual"] is not None:
            close(p_["actual"], a_["actual"], 1e-12, f"actual result {p_['id']}")
    close(P["reverse"]["shocks"], A["reverse"]["shocks"], 1e-9, "reverse stress moves")
    close(P["reverse"]["sigma_m"], A["reverse"]["sigmaM"], 1e-7, "reverse stress sigma")


def test_brinson_matches_v042(portfolio, tmp_path):
    ds = to_dataset(portfolio)
    pol_js = [{"sleeve": s, "weight": 35 if s == "Equities" else 65 if s == "Fixed Income" else 0,
               "series": "Global equities" if s == "Equities" else "Global bonds (synthetic)" if s == "Fixed Income" else ""} for s in ds.sleeves]
    A = run_legacy(to_legacy(ds), {"today": TODAY, "policy": pol_js, "attrFrom": "2025-01", "attrTo": "2026-10"}, tmp_path)["attribution"]
    assert A["ok"], A.get("reason")
    months = [m for m in complete_months(ds, TODAY) if "2025-01" <= m <= "2026-10"]
    policy = {p["sleeve"]: (float(p["weight"]), ds.find_series(p["series"]) if p["series"] else None) for p in pol_js}
    B = brinson(ds, months, policy)
    close(B["Rp"], A["Rp"], 1e-12, "portfolio return")
    close(B["Rb"], A["Rb"], 1e-12, "benchmark return")
    close(B["alloc"], [s["alloc"] for s in A["sleeves"]], 1e-12, "allocation")
    close(B["sel"], [s["sel"] for s in A["sleeves"]], 1e-12, "selection")
