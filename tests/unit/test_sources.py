# ruff: noqa: E501  (the embedded JavaScript test fixture has long lines)
"""web/sources.js: one file per month, actuals over estimates, newest estimate wins, revisions and gaps listed."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the website's source combiner")

JS = r"""
const SRC = require(process.argv[1] + '/web/sources.js');
// a made-up parsed sheet: months [ym, hasReturn], one holding whose value is v[ym]
function pv(sheet, months, v, err) {
  return { sheet, months: months.map(([ym, r]) => ({ ym, hasReturn: r })),
    holdings: [{ name: 'Synthetic Fund', sleeve: 'Equity', liquid: true,
      data: Object.fromEntries(months.map(([ym]) => [ym, { val: v[ym], ret: 0.01, w: 1, err: (err || {})[ym] || null }])) }],
    sleeves: [], total: null, issues: [] };
}
const est23 = { name: 'Dec 23 Estimates.xlsx', kind: SRC.kindFromName('Dec 23 Estimates.xlsx'),
  pvs: [pv("Nov'23 A+R", [['2023-01', true], ['2023-02', true]], { '2023-01': 101, '2023-02': 103 }),
        pv("Oct'23 A+R", [['2023-01', true]], { '2023-01': 99 }),
        pv("Values only", [['2022-06', false]], { '2022-06': 5 })] };
const act23 = { name: 'Management Accounts Dec 23.xlsx', kind: SRC.kindFromName('Management Accounts Dec 23.xlsx'),
  pvs: [pv('2023 Actual Valuations', [['2022-12', false], ['2023-01', true], ['2023-02', true]], { '2022-12': 98, '2023-01': 100, '2023-02': 102 })] };
const est24a = { name: 'March24 Estimates.xlsx', kind: 'estimate', pvs: [pv('2024 Actual Valuations', [['2023-12', false], ['2024-01', true], ['2024-03', true]], { '2023-12': 110, '2024-01': 111, '2024-03': 113 })] };
const est24b = { name: 'Feb24 Estimates.xlsx', kind: 'estimate', pvs: [pv('2024 Actual Valuations', [['2024-01', true], ['2024-02', true]], { '2024-01': 115, '2024-02': 112 }, { '2024-02': '#NAME?' })] };
const c = SRC.combine([est24b, est23, act23, est24a]);
const m = {}; for (const [k, x] of Object.entries(c.months)) m[k] = { file: x.file, kind: x.kind, total: x.total, others: x.others.map(o => [o.file, +o.diff.toFixed(4)]) };
require('fs').writeFileSync(process.argv[2], JSON.stringify({ months: m, gaps: c.gaps, issues: c.issues, nvals: c.vals.length,
  kinds: [est23.kind, act23.kind], valsMonths: c.vals.map(v => v.months.map(x => x.ym)) }));
"""


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    f = tmp_path_factory.mktemp("src") / "o.json"
    subprocess.run(["node", "-e", JS, str(ROOT), str(f)], check=True)
    return json.loads(f.read_text())


def test_kind_from_file_name(out):
    assert out["kinds"] == ["estimate", "actual"]


def test_actuals_beat_estimates_and_revisions_are_listed(out):
    jan = out["months"]["2023-01"]
    assert jan["file"] == "Management Accounts Dec 23.xlsx" and jan["total"] == 100
    assert jan["others"] == [["Dec 23 Estimates.xlsx", 0.01]]  # only the newest sheet of the estimates file is compared


def test_actuals_win_even_without_a_return_and_a_return_beats_an_opening_value(out):
    assert out["months"]["2022-12"]["file"] == "Management Accounts Dec 23.xlsx"  # the only file with Dec 2022
    assert out["months"]["2023-12"]["file"] == "March24 Estimates.xlsx"  # only file with Dec 2023: kept as value only


def test_newest_estimate_wins(out):
    jan24 = out["months"]["2024-01"]
    assert jan24["file"] == "March24 Estimates.xlsx" and jan24["others"] == [["Feb24 Estimates.xlsx", round(115 / 111 - 1, 4)]]
    assert out["months"]["2024-02"]["file"] == "Feb24 Estimates.xlsx"


def test_gaps_errors_and_values_only_sheets_are_reported(out):
    assert out["gaps"] == [["2023-03", "2023-11"]]
    texts = " ".join(i["text"] for i in out["issues"])
    assert "2024-02: 1 holdings show an Excel error in Feb24 Estimates.xlsx" in texts
    assert "values but no monthly returns" in texts and "2022-06" not in out["months"]


def test_each_month_is_passed_on_from_exactly_one_file(out):
    flat = [m for v in out["valsMonths"] for m in v]
    assert sorted(flat) == sorted(out["months"]) and len(flat) == len(set(flat))
