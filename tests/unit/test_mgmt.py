# ruff: noqa: E501  (the embedded JavaScript test fixture has long lines)
"""web/mgmt.js: the management-accounts reader. Made-up workbook rows only.

Checks the flow-free monthly return (Modified Dietz, top-ups at mid-month), that sales and
reclassifications get no return rather than a wrong one, income, unreadable month headers,
and the rules for matching the accounts' short names to the other files by value.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the website's reader")

JS = r"""
const MG = require(process.argv[1] + '/web/mgmt.js');
const serial = (y, m) => Date.UTC(y, m, 0) / 86400000 + 25569;   // month-end of month m (1-12)
const months = [1, 2, 3, 4, 5].map(m => serial(2024, m));
// rows[r][c] is 1-based like the website's xlsx reader: A name, B short ID, C type, D.. months
const R = (a, b, c, vals) => [undefined, a, b, c].concat(vals || []);
function sheet(hdr) {
  const fv = [['Synthetic Alpha Fund', 'Alpha', [100, 102, 113, 113, 110]],   // top-up of 10 in March
              ['Synthetic Beta Fund', 'Beta', [50, 51, 30, 30, 31]],          // partial sale in March
              ['Synthetic Gamma Fund', 'Gamma', [20, 20, 20.2, 20.2, 20.4]],  // cost doubles with no cash: a reclassification
              ['Synthetic Income Fund', 'Inc', [100, 100, 100, 100, 100]],    // pays 1 of income in February
              ['Old Bond', 'Old', [0, 0, 0, 0, 0]]];                          // fully exited before the window
  const cost = [[80, 80, 90, 90, 90], [40, 40, 25, 25, 25], [20, 20, 40, 40, 40], [100, 100, 100, 100, 100], [0, 0, 0, 0, 0]];
  const pe = [['Synthetic Private Equity', 'PE1', [10, 10, 15, 15, 15]]], peCost = [[10, 10, 15, 15, 15]];
  const rows = [undefined, R('Investment', 'P. Pack ID', 'Type', hdr)];
  rows.push(R('Financial assets at fair value'), R('Equity'));
  fv.forEach(([a, b, v]) => rows.push(R(a, b, 'FVTPL', v)));
  rows.push(R('Private Equity')); pe.forEach(([a, b, v]) => rows.push(R(a, b, 'FVTPL', v)));
  rows.push(R('Difference'), R('Financial assets at cost'), R('Equity'));
  fv.forEach(([a, b], i) => rows.push(R(a, b, 'Cost', cost[i])));
  rows.push(R('Private Equity')); pe.forEach(([a, b], i) => rows.push(R(a, b, 'Cost', peCost[i])));
  rows.push(R('Financial assets at cost'));  // a later summary section is ignored
  return rows;
}
const income = MG.parseIncome([undefined, [undefined, 'Income', ...months], [undefined, 'Dividend Income - Synthetic Income Fund', 0, 1, 0, 0, 0]]);
const mp = MG.parse(sheet(months), 'Accounts.xlsx', '2.1 FA by Invest', income);
const ret = {}; mp.holdings.forEach(h => { ret[h.key] = Object.fromEntries(Object.entries(h.data).map(([k, d]) => [k, d.ret])); });
const sleeves = Object.fromEntries(mp.holdings.map(h => [h.key, h.sleeve]));

// a month whose header cell is an Excel error
const hdr2 = months.slice(); hdr2[2] = { err: '#REF!' };
const mp2 = MG.parse(sheet(hdr2), 'Accounts.xlsx', '2.1 FA by Invest', {});
const ret2 = Object.fromEntries(Object.entries(mp2.holdings[0].data).map(([k, d]) => [k, d.ret]));

// name matching by value
const val = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, { val: v, ret: null }]));
const other = { holdings: [
  { name: 'Alpha Estimate', data: val({ '2024-01': 100, '2024-02': 102.02 }) },  // two months within 0.05%: a match
  { name: 'Beta Estimate', data: val({ '2024-01': 50, '2024-02': 52 }) },        // only one month agrees: no match
  { name: 'Income A', data: val({ '2024-01': 100, '2024-02': 100 }) },            // two different holdings both fit Inc: ambiguous
  { name: 'Income B', data: val({ '2024-01': 100, '2024-02': 100 }) } ] };
const auto = MG.matchByValue(mp, [other]);
// one-to-one: two accounts holdings that both fit the same other holding are both left unmatched
const twin = { holdings: [{ key: 'X1', data: val({ '2024-01': 7, '2024-02': 8 }) }, { key: 'X2', data: val({ '2024-01': 7, '2024-02': 8 }) }] };
const twinMatch = MG.matchByValue(twin, [{ holdings: [{ name: 'Seven', data: val({ '2024-01': 7, '2024-02': 8 }) }] }]);
MG.rename(mp, { Alpha: 'Alpha Estimate' });
require('fs').writeFileSync(process.argv[2], JSON.stringify({
  ret, sleeves, keys: mp.holdings.map(h => h.key), names: mp.holdings.map(h => h.name),
  months: mp.months, issues: mp.issues.map(i => i.text), ret2, issues2: mp2.issues.map(i => i.text),
  auto, twinMatch, sheetName: MG.sheetName(['Contents', ' 2.1 FA by Investment ', '7.1 Income']) }));
"""


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    f = tmp_path_factory.mktemp("mg") / "o.json"
    subprocess.run(["node", "-e", JS, str(ROOT), str(f)], check=True)
    return json.loads(f.read_text())


def test_finds_the_sheet_and_skips_exited_holdings(out):
    assert out["sheetName"] == " 2.1 FA by Investment "
    assert out["keys"] == ["Alpha", "Beta", "Gamma", "Inc", "PE1"]
    assert out["sleeves"]["Alpha"] == "Equities" and out["sleeves"]["PE1"] == "Strategic Investments"


def test_first_month_has_no_return(out):
    assert all(r["2024-01"] is None for r in out["ret"].values())
    assert out["months"][0]["hasReturn"] is False and all(m["hasReturn"] for m in out["months"][1:])


def test_a_top_up_is_taken_out_of_the_return_at_mid_month(out):
    a = out["ret"]["Alpha"]
    assert a["2024-02"] == pytest.approx(0.02)
    assert a["2024-03"] == pytest.approx((113 - 102 - 10) / (102 + 10 / 2))  # not (113 / 102 - 1) = 10.8%
    assert a["2024-05"] == pytest.approx(110 / 113 - 1)


def test_a_sale_gives_no_return_rather_than_a_false_loss(out):
    b = out["ret"]["Beta"]
    assert b["2024-03"] is None and b["2024-02"] == pytest.approx(0.02) and b["2024-05"] == pytest.approx(31 / 30 - 1)
    assert any("sale or redemption" in t for t in out["issues"])


def test_a_cost_change_that_is_not_cash_is_left_out_and_flagged(out):
    assert out["ret"]["Gamma"]["2024-03"] is None  # would be -66% after taking out the cost change
    assert any("beyond ±50%" in t and "Gamma" in t for t in out["issues"])


def test_income_is_added_and_capital_calls_are_flagged(out):
    assert out["ret"]["Inc"]["2024-02"] == pytest.approx(0.01)
    assert out["ret"]["PE1"]["2024-03"] == pytest.approx(0.0)
    texts = " ".join(out["issues"])
    assert "capital call" in texts and "income added for 1 holding" in texts


def test_unreadable_month_header_leaves_the_month_and_its_neighbour_out(out):
    r = out["ret2"]
    assert "2024-03" not in r and r["2024-04"] is None and r["2024-02"] == pytest.approx(0.02)
    assert any("no readable date" in t and "2024-03" in t for t in out["issues2"])


def test_name_matching_needs_two_months_one_candidate_and_one_to_one(out):
    assert out["auto"] == {"Alpha": {"to": "Alpha Estimate", "months": 2, "how": "value"}}
    assert out["twinMatch"] == {}
    assert out["names"][0] == "Alpha Estimate" and out["names"][1] == "Beta"
