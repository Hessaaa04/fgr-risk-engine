import json

import numpy as np
import pandas as pd
import pytest

from riskcore.calendar import ym_add
from synthetic import generate
from synthetic.generator import SLEEVES
from synthetic.workbook import write_workbook


@pytest.fixture(scope="module")
def p():
    return generate()


def test_deterministic(p):
    q = generate()
    pd.testing.assert_frame_equal(p.valuations, q.valuations)
    pd.testing.assert_frame_equal(p.flows, q.flows)


def test_shape_matches_the_real_portfolio(p):
    assert set(p.instruments.sleeve) == set(SLEEVES)
    assert set(p.instruments.valuation_method) == {"market_price", "entered_return", "entered_value"}
    assert {"annual", "quarterly", "monthly"} <= set(p.instruments.valuation_frequency)
    assert (p.flows.type == "oil_contribution").sum() > 100
    assert (p.valuations.value >= 0).all()
    assert all(n.startswith("Synthetic ") for n in p.instruments.instrument)


def test_value_bridge_closes(p):
    """V_t = (V_{t-1} + flows_t) x (1 + r_t) for every instrument-month with a return."""
    v = p.valuations.set_index(["instrument", "month"])
    f = p.flows.groupby(["instrument", "month"]).amount.sum()
    worst = 0.0
    for (inst, m), row in v.iterrows():
        if row["return"] is None or pd.isna(row["return"]):
            continue
        prev = v.loc[(inst, ym_add(m, -1)), "value"]
        expect = (prev + f.get((inst, m), 0.0)) * (1 + row["return"])
        worst = max(worst, abs(expect - row["value"]))
    assert worst < 1e-4


def test_stale_assets_report_mostly_zero(p):
    s = p.valuations[p.valuations.instrument.str.contains("Strategic Holding B")]["return"].dropna()
    assert (s == 0).mean() > 0.9


def test_workbook_with_errors(p, tmp_path):
    errs = write_workbook(p, tmp_path / "wb.xlsx", with_errors=True)
    assert len({e["kind"] for e in errs}) == 6
    manifest = json.loads((tmp_path / "wb.errors.json").read_text())
    assert manifest == errs
    val = pd.read_excel(tmp_path / "wb.xlsx", sheet_name="Valuations")
    for e in errs:
        for r in e["excel_rows"]:
            row = val.iloc[r - 2]
            assert row.instrument == e["instrument"] and row.month == e["month"]
    assert set(pd.ExcelFile(tmp_path / "wb.xlsx").sheet_names) == {"Read me", "Instruments", "Valuations", "Flows", "Market data"}
    assert np.isclose(val[val.month == errs[5]["month"]]["return"].max(), 0.41)
