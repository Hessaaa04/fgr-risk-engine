"""Independent validation of riskcore, part 1: does the code compute what the formulas say?

Each check recomputes a riskcore figure by a *different route* (numerical integration,
finite differences, a numerical optimiser, Monte Carlo, pandas, scipy, a textbook case)
rather than re-typing the same formula. Written by the model validator without copying
riskcore code. Synthetic data only.

Run:  python -m pytest validation -q
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import integrate, optimize, stats

from riskcore.active import active_risk
from riskcore.attribution import brinson, carino_k
from riskcore.data import Dataset, Holding, Observation, Series
from riskcore.estimation import EstimationInput, Lineage
from riskcore.factors import factor_exposures, ols, pca
from riskcore.risk import analyse_risk, historical_var_es, max_drawdown, parametric_var_es
from riskcore.smoothing import ar1, geltner, smooth
from riskcore.stress import resolve_scenario, reverse_stress

RNG = np.random.default_rng(7)


def _toy_input(T=60, N=6, seed=1) -> EstimationInput:
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(N, N)) * 0.01
    X = rng.multivariate_normal(np.full(N, 0.005), A @ A.T + np.eye(N) * 1e-4, size=T)
    vals = rng.uniform(1, 10, N)
    hs = [Holding(f"H{i}", "S0" if i < 3 else "S1", True) for i in range(N)]
    lin = [[Lineage.REPORTED] * N for _ in range(T)]
    months = [f"{2015 + t // 12}-{t % 12 + 1:02d}" for t in range(T)]
    return EstimationInput(months[-1], hs, vals, vals / vals.sum(), ["S0", "S1"], np.array([0, 0, 0, 1, 1, 1]), months, X, lin, {})


# ---------------------------------------------------------------- VaR and ES
@pytest.mark.parametrize("conf", [0.90, 0.95, 0.99])
def test_parametric_es_by_numerical_integration(conf):
    sd = 0.031
    z, var, es = parametric_var_es(sd, conf)
    # VaR: the loss exceeded with probability 1-conf
    assert stats.norm(0, sd).sf(var) == pytest.approx(1 - conf, rel=1e-10)
    # ES: average loss in the tail, integrated numerically
    tail, _ = integrate.quad(lambda x: x * stats.norm(0, sd).pdf(x), var, np.inf)
    assert es == pytest.approx(tail / (1 - conf), rel=1e-8)


def test_historical_var_matches_pandas_and_order_statistics():
    r = RNG.standard_t(4, 36) * 0.02
    var, es = historical_var_es(r, 0.95)
    assert var == pytest.approx(-pd.Series(r).quantile(0.05))
    # with 36 months the 5% quantile sits between the 2nd and 3rd worst months
    s = np.sort(r)
    assert -s[2] <= var <= -s[1]
    # ES is the mean of the months at or beyond VaR: here the two worst
    assert es == pytest.approx(-s[:2].mean())


def test_max_drawdown_matches_pandas():
    r = RNG.normal(0.004, 0.03, 132)
    lvl = pd.Series(np.concatenate([[1.0], np.cumprod(1 + r)]))
    assert max_drawdown(r) == pytest.approx((lvl / lvl.cummax() - 1).min())


# ---------------------------------------------------------------- risk decomposition (Euler)
def test_euler_decomposition_by_finite_differences():
    inp = _toy_input()
    R = analyse_risk(inp, 0.95)
    C = np.cov(inp.X, rowvar=False)
    w = inp.w

    def var_of(wv):
        return R.z * math.sqrt(wv @ C @ wv)

    assert R.vol_m == pytest.approx(np.std(inp.X @ w, ddof=1))
    h = 1e-6
    for i, hd in enumerate(R.holdings):
        e = np.zeros_like(w)
        e[i] = h
        assert hd["mvar"] == pytest.approx((var_of(w + e) - var_of(w - e)) / (2 * h), rel=1e-6)
        w0 = w.copy()
        w0[i] = 0  # incremental VaR = sold into cash (weights not rescaled)
        assert hd["ivar"] == pytest.approx(var_of(w) - var_of(w0), rel=1e-9)
    assert sum(hd["cvar"] for hd in R.holdings) == pytest.approx(R.var)
    assert sum(hd["rc"] for hd in R.holdings) == pytest.approx(1.0)
    assert sum(s["cvar"] for s in R.sleeves) == pytest.approx(R.var)


# ---------------------------------------------------------------- active risk
def test_tracking_error_against_handover_formula_and_scipy():
    inp = _toy_input()
    rp = inp.X @ inp.w
    b = rp * 0.8 + RNG.normal(0, 0.01, len(rp))
    bm = Series("B", "benchmark", ret=dict(zip(inp.months, b)))
    a = active_risk(rp, inp.months, bm, 1.645)
    C = np.cov(np.column_stack([inp.X, b]), rowvar=False)
    cB, vB, S = C[:-1, -1], C[-1, -1], C[:-1, :-1]
    te = math.sqrt(12 * (inp.w @ S @ inp.w - 2 * inp.w @ cB + vB))
    assert a["te"] == pytest.approx(te)
    lr = stats.linregress(b, rp)
    assert a["beta"] == pytest.approx(lr.slope)
    assert a["corr"] == pytest.approx(lr.rvalue)


# ---------------------------------------------------------------- factor regressions
def test_ols_against_scipy_lstsq_and_linearity():
    T, K = 60, 5
    F = RNG.normal(0, 0.03, (T, K))
    beta = np.array([1.0, -0.3, 0.5, 0.0, 0.2])
    y = 0.001 + F @ beta + RNG.normal(0, 0.005, T)
    fit = ols(y, F)
    G = np.column_stack([np.ones(T), F])
    coef = np.linalg.solve(G.T @ G, G.T @ y)  # normal equations, a different route
    assert fit["alpha"] == pytest.approx(coef[0])
    np.testing.assert_allclose(fit["beta"], coef[1:], rtol=1e-8)
    # the portfolio beta (weighted holding betas) equals the beta of the portfolio itself
    inp = _toy_input(T=T)
    facs = [Series(f"f{k}", "factor", ret=dict(zip(inp.months, F[:, k]))) for k in range(K)]
    R = analyse_risk(inp, 0.95)
    FE = factor_exposures(inp.X, inp.w, R.rp, inp.months, facs, None, inp.sleeve_idx, R.sleeve_w)
    np.testing.assert_allclose(FE["port"], ols(R.rp, F)["beta"], atol=1e-12)


def test_pca_shares_against_svd():
    inp = _toy_input()
    C = np.cov(inp.X, rowvar=False)
    P = pca(C, inp.w, max_components=6)
    sv = np.linalg.svd(C, compute_uv=False)
    np.testing.assert_allclose([c["share"] for c in P["comps"]], sv / sv.sum(), rtol=1e-8)
    assert sum(c["port_share"] for c in P["comps"]) == pytest.approx(1.0)


# ---------------------------------------------------------------- stress tests
def test_conditional_propagation_against_monte_carlo():
    """s_U = S_UK S_KK^-1 s_K is the mean of the other factors given the specified ones.
    Checked by simulating 400k draws and regressing the unspecified on the specified."""
    K = 5
    A = RNG.normal(size=(K, K))
    SF = A @ A.T / 50
    facs = [Series(n, "factor") for n in ["Global equities", "US Treasuries", "High yield credit", "US dollar", "Oil"]]
    sc = {"id": "x", "kind": "hypothetical", "shocks": {"globalequities": -0.20, "oil": -0.30}}
    out = resolve_scenario(sc, facs, SF, True)["shocks"]
    D = RNG.multivariate_normal(np.zeros(K), SF, 400_000)
    Kn, Un = [0, 4], [1, 2, 3]
    coef, *_ = np.linalg.lstsq(D[:, Kn], D[:, Un], rcond=None)
    mc = np.array([-0.20, -0.30]) @ coef
    np.testing.assert_allclose(out[Un], mc, atol=0.004)


def test_reverse_stress_against_numerical_optimiser():
    K = 5
    A = RNG.normal(size=(K, K))
    SF = A @ A.T / 400
    b = RNG.normal(0.3, 0.4, K)
    rs = reverse_stress(b, SF, 0.10)
    Si = np.linalg.inv(SF)
    res = optimize.minimize(lambda s: s @ Si @ s, np.full(K, -0.05), constraints=[{"type": "eq", "fun": lambda s: b @ s + 0.10}],
                            method="SLSQP", options={"ftol": 1e-14, "maxiter": 500})
    np.testing.assert_allclose(rs["shocks"], res.x, atol=1e-5)
    assert rs["sigma_m"] == pytest.approx(math.sqrt(res.fun), rel=1e-4)


# ---------------------------------------------------------------- attribution
def _one_month_ds(wp, rp, wb, rb):
    hs = []
    for s, (w, r) in enumerate(zip(wp, rp)):
        h = Holding(f"F{s}", f"S{s}", True)
        h.data["2025-01"] = Observation(w * 100, None)
        h.data["2025-02"] = Observation(w * 100 * (1 + r), r)
        hs.append(h)
    ds = Dataset(hs, [f"S{s}" for s in range(len(wp))], ["2025-01", "2025-02"], {"2025-01": False, "2025-02": True})
    pol = {f"S{s}": (wb[s], Series(f"B{s}", "index", ret={"2025-02": rb[s]})) for s in range(len(wp))}
    return ds, pol


def test_brinson_fachler_textbook_case():
    """Three-sector case worked by hand (the standard Brinson-Fachler layout)."""
    wp, rp = [0.40, 0.30, 0.30], [0.20, -0.05, 0.06]
    wb, rb = [0.40, 0.20, 0.40], [0.10, -0.04, 0.08]
    ds, pol = _one_month_ds(wp, rp, wb, rb)
    out = brinson(ds, ["2025-02"], pol)
    Rb = 0.40 * 0.10 + 0.20 * -0.04 + 0.40 * 0.08  # 6.4%
    Rp = 0.40 * 0.20 + 0.30 * -0.05 + 0.30 * 0.06  # 8.3%
    alloc = [0.0, 0.10 * (-0.04 - Rb), -0.10 * (0.08 - Rb)]  # 0, -1.04%, -0.16%
    sel = [0.40 * 0.10, 0.30 * -0.01, 0.30 * -0.02]  # 4.0%, -0.3%, -0.6% (interaction included)
    assert out["Rp"] == pytest.approx(Rp)
    assert out["Rb"] == pytest.approx(Rb)
    np.testing.assert_allclose(out["alloc"], alloc, atol=1e-12)
    np.testing.assert_allclose(out["sel"], sel, atol=1e-12)
    assert out["alloc"].sum() + out["sel"].sum() == pytest.approx(Rp - Rb)


def test_carino_linking_adds_up_over_many_months():
    rp = RNG.normal(0.006, 0.03, 24)
    rb = RNG.normal(0.005, 0.025, 24)
    k = carino_k(np.prod(1 + rp) - 1, np.prod(1 + rb) - 1)
    linked = sum(carino_k(a, b) / k * (a - b) for a, b in zip(rp, rb))
    assert linked == pytest.approx((np.prod(1 + rp) - 1) - (np.prod(1 + rb) - 1), abs=1e-12)


# ---------------------------------------------------------------- desmoothing
def test_geltner_inverts_smoothing_exactly_for_known_phi():
    r = RNG.normal(0.006, 0.04, 120)
    back, phi = geltner(smooth(r, 0.5), 0.5)
    np.testing.assert_allclose(back, r[1:], atol=1e-12)
    assert ar1(r) == pytest.approx(pd.Series(r).autocorr(), abs=0.02)  # same estimator up to the demeaning convention
