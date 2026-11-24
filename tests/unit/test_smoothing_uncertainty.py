import numpy as np
import pytest

from riskcore.smoothing import ar1, geltner, smooth
from riskcore.uncertainty import bootstrap_interval, confidence_label, vol_standard_error


def test_geltner_inverts_smoothing_exactly():
    rng = np.random.default_rng(1)
    true = rng.normal(0.006, 0.04, 120)
    obs = smooth(true, 0.5)
    rec, phi = geltner(obs, phi=0.5)
    assert phi == 0.5
    np.testing.assert_allclose(rec, true[1:], atol=1e-12)


def test_desmoothing_recovers_volatility_on_average():
    """phi is estimated with error (about +/-0.05 with 240 months), so check the average over many samples."""
    ratios, phis = [], []
    for seed in range(50):
        true = np.random.default_rng(seed).normal(0.006, 0.04, 240)
        obs = smooth(true, 0.6)
        assert obs.std() < true.std() * 0.7  # smoothing hides most of the risk
        rec, phi = geltner(obs)
        ratios.append(rec.std() / true.std())
        phis.append(phi)
    assert 0.53 < np.mean(phis) < 0.65
    assert np.mean(ratios) == pytest.approx(1.0, abs=0.1)


def test_desmoothing_refuses_short_history():
    with pytest.raises(ValueError):
        geltner(np.zeros(20))


def test_ar1_of_white_noise_is_small():
    assert abs(ar1(np.random.default_rng(3).normal(size=500))) < 0.1


def test_bootstrap_is_reproducible_and_brackets_estimate():
    r = np.random.default_rng(4).normal(0.005, 0.02, 60)
    a = bootstrap_interval(r, lambda x: x.std(ddof=1))
    b = bootstrap_interval(r, lambda x: x.std(ddof=1))
    assert a == b
    assert a[0] < r.std(ddof=1) < a[1]


def test_vol_standard_error_matches_spec_example():
    # spec 5.3: 60 months -> about 9% of the estimate
    assert vol_standard_error(1.0, 60) == pytest.approx(0.092, abs=0.001)


@pytest.mark.parametrize("args,label", [
    ((60, 1.0, 0.0, 0.0), "High"),
    ((60, 1.0, 0.0, 0.10), "Medium"),
    ((48, 0.9, 0.0, 0.0), "Medium"),
    ((24, 1.0, 0.0, 0.0), "Low"),
    ((60, 1.0, 0.0, 0.30), "Low"),
])
def test_confidence_label(args, label):
    assert confidence_label(*args) == label
