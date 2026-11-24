"""Corrections for smoothed and quarterly-valued holdings (riskcore.illiquid; validation V-01, V-03)."""

from __future__ import annotations

import pytest

from riskcore.analyse import Settings, analyse
from riskcore.estimation import Lineage
from synthetic import generate
from synthetic.adapters import to_dataset

ST = dict(today="2026-01-15", as_of="2025-12", window=36, risk_benchmark="50/50 reference (synthetic)")
PE = "Synthetic Private Equity Fund A"
PROP = "Synthetic Property Fund A"


@pytest.fixture(scope="module")
def p():
    return generate()


def test_off_reproduces_unadjusted(p):
    a = analyse(to_dataset(p), Settings(**ST, desmooth=False))
    assert a["adjustments"] == []
    assert a["lineage"][Lineage.DESMOOTHED.value] == 0 and a["lineage"][Lineage.FACTOR_MODEL.value] == 0


def test_contributions_still_add_up_with_extra_variance(p):
    a = analyse(to_dataset(p), Settings(**ST))
    R = a["risk"]
    assert sum(h["rc"] for h in R.holdings) == pytest.approx(1.0, abs=1e-12)
    assert sum(h["cvar"] for h in R.holdings) == pytest.approx(R.var, abs=1e-12)  # Euler: contributions sum to VaR


def test_cash_is_not_desmoothed(p):
    a = analyse(to_dataset(p), Settings(**ST))
    assert not any("Cash" in x["name"] for x in a["adjustments"])


def test_assumed_beta_for_annual_fund(p):
    a = analyse(to_dataset(p), Settings(**ST, assumed_betas={PROP: 0.6}))
    adj = next(x for x in a["adjustments"] if x["name"] == PROP)
    assert adj["method"] == "assumed beta" and adj["beta"] == 0.6
    names = [h["name"] for h in a["risk"].holdings]
    assert a["factors"]["B"][names.index(PROP)][0] == pytest.approx(0.6, abs=1e-9)


def test_annual_fund_without_assumption_is_flagged_not_fitted(p):
    a = analyse(to_dataset(p), Settings(**ST))
    adj = next(x for x in a["adjustments"] if x["name"] == PROP)
    assert adj["method"] == "needs an assumed beta or proxy"


def test_modelled_cells_lower_the_label_inputs(p):
    a = analyse(to_dataset(p), Settings(**ST))
    assert a["lineage"]["factor_model"] > 0 and a["lineage"]["desmoothed"] > 0
    assert a["lineage"]["reported"] < 0.95
