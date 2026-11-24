"""Hand-calculated cases: small enough to check on paper."""
import math

import numpy as np
import pytest
from scipy import stats

from riskcore.risk import covariance, historical_var_es, max_drawdown, parametric_var_es


def test_two_asset_volatility_by_hand():
    X = np.array([[0.01, 0.02], [-0.01, 0.00], [0.03, 0.01], [-0.03, -0.03]])
    C = covariance(X)
    # asset 1: mean 0, squares sum 0.002 -> var 0.002/3
    assert C[0, 0] == pytest.approx(0.002 / 3)
    w = np.array([0.5, 0.5])
    rp = X @ w
    assert math.sqrt(w @ C @ w) == pytest.approx(rp.std(ddof=1))


def test_parametric_var_es_formula():
    z, var, es = parametric_var_es(0.02, 0.95)
    assert z == pytest.approx(1.6448536269514722)
    assert var == pytest.approx(0.02 * 1.6448536269514722)
    assert es == pytest.approx(0.02 * stats.norm.pdf(z) / 0.05)
    assert es > var


def test_historical_var_es():
    r = np.array([-0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.01, -0.01, 0.02, 0.04])
    var, es = historical_var_es(r, 0.90)
    q = np.quantile(r, 0.10)  # -0.023
    assert var == pytest.approx(-q)
    assert es == pytest.approx(0.05)


def test_drawdown_by_hand():
    # up 10%, down 20%, up 5%: peak 1.10, trough 0.88 -> -20%
    assert max_drawdown(np.array([0.10, -0.20, 0.05])) == pytest.approx(-0.20)
    assert max_drawdown(np.array([0.01, 0.02])) == 0.0
