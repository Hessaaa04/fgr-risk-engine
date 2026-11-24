"""Validator findings on riskcore.liquidity_profile (PR #6), written as tests. Synthetic data only.
Open findings are strict xfails: a fix makes them pass, CI flags it, and the validator re-reviews."""

from __future__ import annotations

import pytest

from riskcore.liquidity_profile import Position, Profile, analyse


def _profile():
    return Profile("2026-07-31", [
        Position("Synthetic Cash A", "Cash & Equivalents", 100.0, "liquid", None, None),
        Position("Synthetic Cash B", "Cash & Equivalents", 50.0, "liquid", "daily", 0),
        Position("Synthetic Equity", "Equities", 300.0, "liquid", "daily", 3),
        Position("Synthetic Property", "Alternative", 100.0, "illiquid", "semi-annually", None),
        Position("Synthetic PE", "Alternative", 250.0, "illiquid", "illiquid until maturity", None, True),
    ])


@pytest.mark.xfail(strict=True, reason="L-1: a cash account with blank max days counts as 0 in the ladder and the limit")
def test_l1_cash_is_available_at_day_one():
    o = analyse(_profile())
    day1 = next(x for x in o["ladder"] if x["days"] == 1)
    assert day1["share"] == pytest.approx(150 / 800)  # today 50/800: only the cash row with a day count


@pytest.mark.xfail(strict=True, reason="L-2: a semi-annual or annual fund with blank max days is never available and is not flagged")
def test_l2_missing_max_days_outside_maturity_is_flagged():
    o = analyse(_profile())
    assert any(c["name"] == "Synthetic Property" for c in o["checks"])
