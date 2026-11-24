"""Write a SyntheticPortfolio to Excel, optionally with deliberate data errors.

The 'with errors' workbook is test material for the Phase 1 validation rules:
each injected error is listed in errors.json with its sheet, row and expected rule,
so a test can check that validation catches every one.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .generator import GENERATOR_VERSION, SyntheticPortfolio

README = [
    ["Synthetic portfolio workbook"],
    ["Every name and number in this file is generated. None of it comes from real holdings."],
    ["Generator version", GENERATOR_VERSION],
    ["Seed", None],
    ["Sheets", "Instruments (reference data), Valuations (month-end value and reported return), "
               "Flows (contributions, withdrawals, subscriptions, transfers), Market data (monthly returns)"],
    ["Conventions", "USD. Returns are decimals per month. Value = month-end value. Money added counts from the start of the month."],
]


def inject_errors(val: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, list[dict]]:
    """Return a copy of the valuations with six kinds of realistic error, and a manifest of them."""
    rng = np.random.default_rng(seed + 1)
    v = val.drop(columns=["true_return"]).reset_index(drop=True).copy()
    errs: list[dict] = []
    months = sorted(v.month.unique())

    def pick(mask):
        idx = v.index[mask]
        return int(idx[rng.integers(len(idx))])

    # 1. a month that repeats the previous month's figures
    i = pick((v.month == months[70]) & v.instrument.str.contains("Equity Fund A"))
    prev = v.index[(v.month == months[69]) & (v.instrument == v.at[i, "instrument"])][0]
    v.loc[i, ["value", "return"]] = v.loc[prev, ["value", "return"]].values
    errs.append({"kind": "repeat_previous_month", "instrument": v.at[i, "instrument"], "month": v.at[i, "month"], "rule": "value_and_return_identical_to_prior_month"})
    # 2. a value typed in thousands
    i = pick((v.month == months[90]) & v.instrument.str.contains("Bond Fund A"))
    v.at[i, "value"] = v.at[i, "value"] / 1000
    errs.append({"kind": "value_in_thousands", "instrument": v.at[i, "instrument"], "month": v.at[i, "month"], "rule": "value_change_not_explained_by_return_and_flows"})
    # 3. a missing return for an entered-return holding
    i = pick((v.month == months[100]) & v.instrument.str.contains("Bond Fund D"))
    v.at[i, "return"] = None
    errs.append({"kind": "missing_return", "instrument": v.at[i, "instrument"], "month": v.at[i, "month"], "rule": "required_field_missing"})
    # 4. an instrument name the master does not know
    i = pick((v.month == months[110]) & v.instrument.str.contains("Multi-Asset Fund B"))
    v.at[i, "instrument"] = "Synthetic Multi Asset Fnd B"
    errs.append({"kind": "unknown_instrument", "instrument": "Synthetic Multi Asset Fnd B", "month": v.at[i, "month"], "rule": "identifier_not_in_instrument_master"})
    # 5. a duplicated row
    i = pick((v.month == months[120]) & v.instrument.str.contains("Hedge Fund A"))
    v = pd.concat([v, v.loc[[i]]], ignore_index=True)
    errs.append({"kind": "duplicate_row", "instrument": v.at[i, "instrument"], "month": v.at[i, "month"], "rule": "duplicate_instrument_month"})
    # 6. a return far outside the normal range for a listed fund
    i = pick((v.month == months[125]) & v.instrument.str.contains("Equity Fund B"))
    v.at[i, "return"] = 0.41
    errs.append({"kind": "outlier_return", "instrument": v.at[i, "instrument"], "month": v.at[i, "month"], "rule": "return_outside_plausible_range"})
    v = v.sort_values(["month", "instrument"], kind="stable").reset_index(drop=True)
    for e in errs:
        rows = v.index[(v.instrument == e["instrument"]) & (v.month == e["month"])]
        e["excel_rows"] = [int(r) + 2 for r in rows]  # header is row 1
    return v, errs


def write_workbook(p: SyntheticPortfolio, path: str | Path, with_errors: bool = False) -> list[dict]:
    path = Path(path)
    val = p.valuations.drop(columns=["true_return"])
    errs: list[dict] = []
    if with_errors:
        val, errs = inject_errors(p.valuations, p.seed)
    readme = [row[:] for row in README]
    readme[3][1] = p.seed
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame(readme).to_excel(xw, sheet_name="Read me", index=False, header=False)
        p.instruments.to_excel(xw, sheet_name="Instruments", index=False)
        val.to_excel(xw, sheet_name="Valuations", index=False)
        p.flows.to_excel(xw, sheet_name="Flows", index=False)
        p.market.rename_axis("month").reset_index().to_excel(xw, sheet_name="Market data", index=False)
    if with_errors:
        path.with_suffix(".errors.json").write_text(json.dumps(errs, indent=2))
    return errs
