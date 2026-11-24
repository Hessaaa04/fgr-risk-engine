"""Write the synthetic portfolio in the same Excel layout v0.4.2 reads (and so the website reads).

Gives a made-up file to test the website's 'load Excel' page end to end, without real data:
- "Actual Valuations": row 1 holds month-end dates; each month has a value column and an
  "M-% Return" column; column A = Liquid/Illiquid flag, B = asset class, C = name;
  a sleeve row (no flag) precedes its holdings; a "Portfolio" total row ends the table.
- "Market manual": row 1 series names, row 2 types, column A month-end dates, values in percent.
"""

from __future__ import annotations

import calendar
import datetime as dt
from pathlib import Path

from openpyxl import Workbook

from .generator import SLEEVES, SyntheticPortfolio


def _month_end(ym: str) -> dt.date:
    y, m = int(ym[:4]), int(ym[5:7])
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def write_v042_workbook(p: SyntheticPortfolio, path: str | Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    ws["A1"] = "Synthetic portfolio in the v0.4.2 workbook layout. Every name and number is made up."
    va = wb.create_sheet("Actual Valuations")
    months = list(p.months)
    v = p.valuations.set_index(["instrument", "month"])
    va.cell(1, 1, "Liquidity")
    va.cell(1, 2, "Asset class")
    va.cell(1, 3, "Holding")
    for k, m in enumerate(months):
        c = 4 + 2 * k
        va.cell(1, c, _month_end(m)).number_format = "yyyy-mm-dd"
        va.cell(1, c + 1, "M-% Return")
    inst = p.instruments.set_index("instrument")
    row = 2

    def put(r, inst_names):
        for k, m in enumerate(months):
            c = 4 + 2 * k
            vals = [v.loc[(n, m)] if (n, m) in v.index else None for n in inst_names]
            vals = [x for x in vals if x is not None]
            if not vals:
                continue
            tot = sum(float(x["value"]) for x in vals)
            if len(inst_names) == 1:
                x = vals[0]
                va.cell(r, c, float(x["value"]))
                if x["return"] == x["return"]:  # not NaN
                    va.cell(r, c + 1, float(x["return"]))
            elif tot > 0:
                va.cell(r, c, tot)

    for s in SLEEVES:
        names = [n for n in inst.index if inst.loc[n, "sleeve"] == s]
        if not names:
            continue
        va.cell(row, 2, s)
        va.cell(row, 3, s)
        put(row, names)
        row += 1
        for n in names:
            va.cell(row, 1, "Liquid" if bool(inst.loc[n, "liquid"]) else "Illiquid")
            va.cell(row, 2, s)
            va.cell(row, 3, n)
            put(row, [n])
            row += 1
    va.cell(row, 2, "Portfolio")
    put(row, list(inst.index))

    mm = wb.create_sheet("Market manual")
    mm.cell(1, 1, "Month")
    mm.cell(2, 1, "Type")
    meta = list(p.market_meta.itertuples(index=False))
    for j, r in enumerate(meta):
        mm.cell(1, 2 + j, r.name)
        mm.cell(2, 2 + j, r.type)
    for i, m in enumerate(p.market.index):
        mm.cell(3 + i, 1, _month_end(m)).number_format = "yyyy-mm-dd"
        for j, r in enumerate(meta):
            x = p.market.loc[m, r.name]
            if x == x:
                mm.cell(3 + i, 2 + j, float(x) * 100)
    wb.save(path)
