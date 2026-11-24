"""The website's glue (webapp.bridge) passes riskcore's numbers through unchanged and handles odd input safely."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from riskcore.analyse import Settings, analyse
from riskcore.performance import compare, cumulative, rolling_vol, series_stats
from riskcore.smoothing import observed_frequency
from synthetic import generate
from synthetic.adapters import to_dataset, to_legacy
from webapp import bridge

TODAY = "2026-11-24"


@pytest.fixture(scope="module")
def loaded():
    p = generate()
    meta = json.loads(bridge.load(json.dumps(to_legacy(to_dataset(p))), TODAY))
    return p, meta


def test_run_matches_riskcore(loaded):
    p, meta = loaded
    out = json.loads(bridge.run(json.dumps({"window": 36, "conf": 0.99})))
    P = analyse(to_dataset(p), Settings(today=TODAY, window=36, conf=0.99, risk_benchmark=meta["defaults"]["risk"], perf_benchmark=meta["defaults"]["perf"]))
    R = P["risk"]
    assert out["headline"]["vol"] == pytest.approx(R.vol_a, abs=1e-15)
    assert out["headline"]["var"] == pytest.approx(R.var, abs=1e-15)
    assert out["headline"]["es"] == pytest.approx(R.es, abs=1e-15)
    assert out["quality"]["label"] == P["confidence_label"]
    assert [h["rc"] for h in out["holdings"]] == pytest.approx([h["rc"] for h in R.holdings], abs=1e-15)
    lo, hi = out["headline"]["vol_range"]
    assert lo < R.vol_a < hi
    # the last rolling point is today's estimate
    assert out["rolling"]["months"][-1] == out["as_of"]
    assert out["rolling"]["vol"][-1] == pytest.approx(R.vol_a, abs=1e-15)


def test_scenario_and_reverse(loaded):
    json.loads(bridge.run(json.dumps({"window": 60})))
    x = json.loads(bridge.scenario(json.dumps({"Global equities": -0.2}), False))
    assert x["shocks"][0] == -0.2 and all(v == 0 for v in x["shocks"][1:])  # nothing else moves without propagation
    assert x["port"] == pytest.approx(sum(h["impact"] for h in x["holdings"]), abs=1e-12)
    assert x["port"] == pytest.approx(sum(s["impact"] for s in x["by_sleeve"]), abs=1e-12)
    preset = next(s for s in json.loads(bridge.run(json.dumps({"window": 60})))["stress"] if s["id"] == "eq20")
    y = json.loads(bridge.scenario(json.dumps({"Global equities": -0.2}), True))
    assert y["port"] == pytest.approx(preset["port"], abs=1e-12)  # builder reproduces the preset
    r = json.loads(bridge.reverse(0.1))
    assert r["loss"] == 0.1


def test_attribution_missing_index_is_reported_not_crash(loaded):
    _, meta = loaded
    bridge.run(json.dumps({}))
    pol = [{"sleeve": s, "weight": 50 if s in ("Equities", "Alternative") else 0, "series": "Global equities" if s == "Equities" else ""} for s in meta["sleeves"]]
    a = json.loads(bridge.attribution("2026-01", "2026-10", json.dumps(pol)))
    assert not a["ok"] and "no benchmark index" in a["reason"]
    assert a["contrib"]  # contributions still shown


def test_comparison_hand_check():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    rng = np.random.default_rng(1)
    b = rng.normal(0.005, 0.03, 12)
    p = 0.001 + 1.2 * b + rng.normal(0, 0.01, 12)
    c = compare(dict(zip(months, p)), dict(zip(months, b)), months)
    a = p - b
    assert c["te"] == pytest.approx(a.std(ddof=1) * math.sqrt(12))
    assert c["beta"] == pytest.approx(np.polyfit(b, p, 1)[0])
    assert c["ir"] == pytest.approx(a.mean() * 12 / c["te"])
    assert c["port"]["total"] == pytest.approx(np.prod(1 + p) - 1)
    assert series_stats(p)["ann_return"] == pytest.approx(np.prod(1 + p) - 1)  # 12 months: annualised = total


def test_missing_is_never_zero():
    months = ["2025-01", "2025-02", "2025-03"]
    assert cumulative({"2025-01": 0.1, "2025-02": None, "2025-03": 0.1}, months) == [pytest.approx(1.1), None, None]
    assert compare({"2025-01": 0.1}, {"2025-01": 0.1}, months) == {"n": 1}
    assert rolling_vol({"2025-01": 0.1, "2025-02": None, "2025-03": 0.0}, months, 2) == [None, None, None]


def test_observed_frequency():
    ms = [f"{y}-{m:02d}" for y in range(2016, 2026) for m in range(1, 13)]
    assert observed_frequency({m: 0.01 for m in ms}) == "monthly"
    assert observed_frequency({m: (0.03 if int(m[5:]) % 3 == 0 else 0.0) for m in ms}) == "quarterly"
    assert observed_frequency({m: (0.08 if m.endswith("-12") else 0.0) for m in ms}) == "annual"
    assert observed_frequency({m: 0.0 for m in ms}) == "unknown"
