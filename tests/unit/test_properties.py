"""Invariants that must hold for any portfolio (spec Section 9.4, property tests)."""
import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from riskcore.data import Holding, Observation
from riskcore.estimation import EstimationInput, Lineage
from riskcore.risk import analyse_risk
from riskcore.stress import reverse_stress


def make_input(seed: int, T: int, N: int) -> EstimationInput:
    rng = np.random.default_rng(seed)
    X = rng.normal(0.005, 0.03, (T, N)) + rng.normal(0, 0.02, (T, 1))
    v = rng.uniform(1, 10, N)
    w = v / v.sum()
    sidx = np.arange(N) % 3
    pos = [Holding(f"H{i}", f"S{sidx[i]}", bool(i % 2), {"2026-01": Observation(v[i], 0.0)}) for i in range(N)]
    lin = [[Lineage.REPORTED] * N for _ in range(T)]
    return EstimationInput("2026-01", pos, v, w, ["S0", "S1", "S2"], sidx, [f"m{t}" for t in range(T)], X, lin, {})


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), T=st.integers(12, 80), N=st.integers(3, 15))
def test_risk_decomposition_adds_up(seed, T, N):
    R = analyse_risk(make_input(seed, T, N), 0.95)
    assert abs(sum(h["rc"] for h in R.holdings) - 1) < 1e-10
    assert abs(sum(h["cvar"] for h in R.holdings) - R.var) < 1e-12
    assert abs(sum(s["rc"] for s in R.sleeves) - 1) < 1e-10
    assert abs(R.sleeve_w.sum() - 1) < 1e-12
    assert R.es >= R.var >= 0
    assert R.max_dd <= 0


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10_000), loss=st.floats(0.01, 0.5))
def test_reverse_stress_hits_the_target_loss(seed, loss):
    rng = np.random.default_rng(seed)
    A = rng.normal(0, 0.03, (40, 4))
    SF = np.cov(A, rowvar=False)
    b = rng.normal(0.5, 0.5, 4)
    r = reverse_stress(b, SF, loss)
    assert abs(b @ r["shocks"] + loss) < 1e-12
