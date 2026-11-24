"""Liquidity report: buckets, ladder, gates and the checks, on hand cases and a made-up workbook."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from riskcore.liquidity_profile import Position, Profile, Terms, analyse, bucket
from synthetic.liquidity_workbook import sheet_rows, write_liquidity_workbook
from webapp import bridge
from webapp.liquidity_reader import read_report

ROOT = Path(__file__).resolve().parents[2]


def P(name="F", days=None, timeline="daily", value=100.0, ac="Equity", label=None, plus=False, comments=None):
    return Position(name=name, asset_class=ac, value=value, label=label, timeline=timeline, max_days=days, no_redemption=plus, comments=comments)


@pytest.mark.parametrize("days,expected", [(1, "immediate"), (5, "immediate"), (6, "short_term"), (15, "short_term"), (16, "monthly"),
                                           (40, "monthly"), (41, "st_quarterly"), (60, "st_quarterly"), (61, "lt_quarterly"), (400, "lt_quarterly")])
def test_bucket_edges_are_inclusive_with_no_gaps(days, expected):
    assert bucket(P(days=days, timeline="Quarterly")) == expected


def test_timeline_and_missing_terms():
    assert bucket(P(days=120, timeline="Semi Annually")) == "extended"
    assert bucket(P(days=365, timeline="Annually", ac="Cash & Equivalents")) == "extended"  # receivables
    assert bucket(P(timeline="Illiquid until maturity / expiry ", plus=True)) == "maturity"
    assert bucket(P(timeline="Permenant illiquid holdings ", plus=True)) == "permanent"  # the report's spelling
    assert bucket(P(days=1, ac="Cash & Equivalents")) == "cash"
    assert bucket(P(plus=True, timeline="Quarterly")) == "maturity"  # "+" = no redemption right: never 0 days
    assert bucket(P(days=None, timeline="Quarterly")) == "unknown"  # blank: never guessed


def test_unknown_counts_against_the_limit_and_missing_value_is_not_zero():
    a = analyse(Profile("2030-07-31", [P("A", 3), P("B", None, "Quarterly"), P("C", 3, value=None)]), min_liquid=0.6)
    assert a["aum"] == 200  # C has no value: left out, not counted as 0
    assert a["unknown"] == 0.5 and a["illiquid_for_limits"] == 0.5
    assert a["limit"]["available"] == 0.5 and not a["limit"]["ok"]
    assert {c["name"] for c in a["checks"] if c["level"] == "error"} == {"B", "C"}


def test_gate_releases_over_dealing_dates_lockup_and_fee():
    pr = Profile("2030-07-31", [P("G", 30, "Quarterly"), P("L", 5), P("X", 5)])
    t = {"G": Terms(gate=0.25), "L": Terms(lockup_end="2030-12-31"), "X": Terms(fee=0.02)}
    a = analyse(pr, horizon=60, terms=t)
    lad = {x["days"]: x for x in a["ladder"]}
    assert lad[40]["value"] == 300 and lad[40]["with_terms"] == pytest.approx(25 + 98)  # first dealing date: 25%; fee 2%
    assert lad[180]["with_terms"] == pytest.approx(25 * 2 + 100 + 98)  # dealing dates at 30, 121, 212 days: two by day 180
    assert lad[365]["with_terms"] == pytest.approx(100 + 100 + 98)  # four quarters at 25%; lock-up ended
    assert a["limit"]["available"] == pytest.approx(123 / 300)


def test_stressed_view_suspends_quarterly_funds_only():
    a = analyse(Profile("2030-07-31", [P("Q", 30, "Quarterly"), P("D", 3)]), suspend_quarterly=0.5)
    lad = {x["days"]: x for x in a["ladder"]}
    assert lad[60]["with_terms"] == 200 and lad[60]["stressed"] == 150


def test_label_mismatch_and_gate_mention_are_flagged():
    a = analyse(Profile(None, [P("L", 90, "Quarterly", label="liquid"), P("I", 10, label="illiquid"),
                               P("G", 5, comments="Gate of 25% per quarter")]))
    txt = {c["name"]: c["text"] for c in a["checks"]}
    assert "labelled Liquid" in txt["L"] and "labelled Illiquid" in txt["I"] and "gate" in txt["G"]
    a = analyse(Profile(None, [P("G", 5, comments="Gate of 25% per quarter")]), terms={"G": Terms(gate=0.25)})
    assert not a["checks"]


def test_made_up_workbook_end_to_end(tmp_path):
    exp = write_liquidity_workbook(tmp_path / "liq.xlsx")
    pr, issues = read_report(sheet_rows(tmp_path / "liq.xlsx"), "liq.xlsx")
    assert pr.as_of == "2030-07-31" and len(pr.positions) == 17 and not issues
    a = analyse(pr)
    got = {b["key"]: b["value"] for b in a["buckets"]}
    assert got == pytest.approx(exp)
    rec = {r.get("bucket", r["item"]): r for r in a["reconciliation"]}
    assert rec["Total AUM"]["diff"] == 0
    assert rec["permanent"]["diff"] == 15e6 and all(r["diff"] == 0 for k, r in rec.items() if k != "permanent")
    kinds = [c["text"] for c in a["checks"]]
    assert any("extra spaces" in t for t in kinds)
    assert any("labelled Liquid" in t and "90 days" in t for t in kinds)
    assert any("gate" in t.lower() for t in kinds) and any("Lock up" in t for t in kinds)
    assert any("no maximum days" in t for t in kinds)
    assert a["not_captured"]  # unfunded commitments are named as missing, not silently left out
    pr2, _ = read_report(sheet_rows(tmp_path / "liq.xlsx"), "liq.xlsx", receivables=True)
    a2 = analyse(pr2)
    assert a2["aum"] == a["aum"] + 12e6 and {b["key"]: b["value"] for b in a2["buckets"]}["extended"] == 35e6 + 12e6


READ = """
const XL=require(process.argv[1]+'/legacy/v0_4_2/xlsx.js'), fs=require('fs');
const b=fs.readFileSync(process.argv[2]); const wb=XL.open(b.buffer.slice(b.byteOffset,b.byteOffset+b.length));
const sheets={}; wb.sheetNames.forEach(n=>{ sheets[n]=wb.sheet(n,400); });
fs.writeFileSync(process.argv[3], JSON.stringify([{name:'liq.xlsx', sheets}]));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run the website's Excel reader")
def test_website_reader_route(tmp_path):
    write_liquidity_workbook(tmp_path / "liq.xlsx")
    subprocess.run(["node", "-e", READ, str(ROOT), str(tmp_path / "liq.xlsx"), str(tmp_path / "f.json")], check=True)
    out = json.loads(bridge.liquidity((tmp_path / "f.json").read_text(), json.dumps({"min_liquid": 0.75, "horizon": 60})))
    a = out["profiles"][0]
    assert a["as_of"] == "2030-07-31" and a["aum"] == pytest.approx(675e6) and not out["issues"]
    assert a["limit"]["available"] == pytest.approx((65 + 120 + 110 + 130 + 55) / 675)
    two = json.loads(bridge.liquidity(json.dumps(json.loads((tmp_path / "f.json").read_text()) * 2), "{}"))
    assert len(two["profiles"]) == 2 and not any(c["moved"] for c in two["change"])
