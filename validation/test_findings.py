"""Independent validation of riskcore, part 2: findings, written as tests.

Each test states what a correct engine should do. An open finding is marked `xfail(strict=True)`:
it is expected to fail until fixed. When the builder fixes a finding, its test starts passing,
pytest reports "XPASS (strict)" as a failure, and the fix must be re-reviewed by the
validator, who then removes the marker. Finding ids (V-xx) match
validation/riskcore-0.1.0.md. Synthetic data only.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from riskcore.analyse import Settings, analyse
from riskcore.attribution import brinson
from riskcore.data import norm
from synthetic.adapters import to_dataset
from synthetic.generator import _specs, generate

AS_OF = "2025-12"
TODAY = "2026-01-15"
PE = "Synthetic Private Equity Fund A"


@pytest.fixture(scope="module")
def port():
    return generate()


@pytest.fixture(scope="module")
def run36(port):
    ds = to_dataset(port)
    return analyse(ds, Settings(today=TODAY, as_of=AS_OF, window=36, risk_benchmark="50/50 reference (synthetic)"))


# V-01: fixed in PR #4, kept as a regression test (validator re-review 24 Nov 2026)
def test_v01_portfolio_vol_within_10pct_of_true_vol(port, run36):
    """The synthetic generator keeps each fund's true (unsmoothed) return, so we know the right answer."""
    tr = port.valuations.pivot(index="month", columns="instrument", values="true_return")
    names = [h["name"] for h in run36["risk"].holdings]
    Xt = tr.loc[run36["months"], names].to_numpy()
    Xt = np.where(np.isnan(Xt), run36["X"], Xt)
    true_vol = float((Xt @ run36["w"]).std(ddof=1) * math.sqrt(12))
    assert run36["risk"].vol_a >= 0.9 * true_vol  # today: 7.9% reported vs 9.1% true


# V-02: fixed in PR #4, kept as a regression test (validator re-review 24 Nov 2026)
def test_v02_quarterly_valued_fund_flagged_stale(run36):
    pe = next(h for h in run36["risk"].holdings if h["name"] == PE)
    assert pe["stale"]


# V-03: fixed in PR #4, kept as a regression test (validator re-review 24 Nov 2026)
def test_v03_private_equity_equity_beta_roughly_right(run36):
    names = [h["name"] for h in run36["risk"].holdings]
    true_beta = next(s.betas[0] for s in _specs() if s.name == PE)  # 1.2
    est = run36["factors"]["B"][names.index(PE)][0]  # today: about -0.3
    assert abs(est - true_beta) < 0.5


# V-04: fixed in PR #4, kept as a regression test (validator re-review 24 Nov 2026)
def test_v04_unrecognised_factor_names_are_not_silently_zero(port):
    ds = to_dataset(port)
    new = {}
    for s in ds.series.values():
        if s.type == "factor":
            s.name = s.name + " (Bloomberg)"
        new[norm(s.name)] = s
    ds.series = new
    out = analyse(ds, Settings(today=TODAY, as_of=AS_OF, window=36))
    eq20 = next(r for r in out["stress"] if r["id"] == "eq20")
    assert eq20["port"] != 0.0  # today: every hypothetical scenario shows exactly 0.0, with no warning


# V-05: fixed in PR #4, kept as a regression test (validator re-review 24 Nov 2026)
def test_v05_brinson_policy_weight_without_index(port):
    ds = to_dataset(port)
    pol = {"Equities": (0.35, ds.find_series("Global equities")),
           "Fixed Income": (0.55, ds.find_series("Global bonds (synthetic)")),
           "Alternative": (0.10, None)}
    out = brinson(ds, ["2025-01", "2025-02", "2025-03"], pol)
    assert out["alloc"].sum() + out["sel"].sum() == pytest.approx(out["excess"])


# V-17: fixed in 8e48d2f, kept as a regression test (validator re-review 24 Nov 2026)
def test_v17_one_factor_per_role_unless_mapped():
    from riskcore.data import Series
    from riskcore.stress import factor_roles
    fs = [Series("Global equities", "factor", "SYN-EQ"), Series("EM equities", "factor", "SYN-EM")]
    roles = factor_roles(fs)
    assert roles.count("globalequities") <= 1  # today both are 'globalequities', so EM is shocked -20% in 'Equities fall 20%'


@pytest.mark.xfail(strict=True, reason="V-18 (Low, accepted limitation): 40 quarters cannot identify within-quarter smoothing; 16.8% vs 19.9% true after the 0.5 floor")
def test_v18_private_equity_vol_within_15pct_of_true(port, run36):
    tr = port.valuations.pivot(index="month", columns="instrument", values="true_return")
    true_vol = float(tr.loc[run36["months"], PE].std(ddof=1) * math.sqrt(12))
    pe = next(h for h in run36["risk"].holdings if h["name"] == PE)
    assert pe["vol_a"] >= 0.85 * true_vol  # after 8e48d2f: 16.8% modelled vs 19.9% true (84.5%); do not tune the floor to pass this
