"""Write a made-up liquidity report in the same layout as FGR's monthly "Liquidity Profile" workbook.

Every name and number is invented. The file has deliberate faults so tests can check that they are
caught: a label with a trailing space, a "Liquid" label on a 90-day fund, a comment that mentions a
gate with no entered terms, a holding with blank max days, and a dashboard figure that leaves out
one permanent holding (as a SUMIFS range that stops one row short would).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
from openpyxl import Workbook

TERMS_SHEET = "Portfolio Liq. Terms & NAV "  # the real sheet name ends with a space
HEADER = ["Asset Class", "Name", "Allocation ", "Valuations(USD,mn) ", "Liquidity", "Timeline ", "PMT of Proceeds", "Max Days", "Comments", "Source"]

# (asset class, name, value USD, label, timeline, payment, max days, comment)
HOLDINGS = [
    ("Cash & Equivalents", "Cash Accounts (Principal Only)", 40e6, "Liquid", "daily", "T+1", 1, None),
    ("Cash & Equivalents", "Time Deposits (Principal Only)", 25e6, "Liquid", "daily", "T+2", 2, "-"),
    ("Equity", "Synthetic Global Equity Index", 120e6, "Liquid", "daily", "T+2", 5, None),
    ("Equity", "Synthetic US Equity", 80e6, "Liquid ", "daily", "T+3", 6, "No redemption charges"),
    ("Equity", "Synthetic Japan Equity", 30e6, "Liquid", "daily", "T+3", 15, None),
    ("Fixed Income", "Synthetic Global Bond", 90e6, "Liquid", "daily", "T+4", 16, None),
    ("Fixed Income", "Synthetic Credit Mandate", 40e6, "Liquid", "Monthly", "T+32", 40, None),
    ("Fixed Income", "Synthetic Tactical Credit", 35e6, "Illiquid", "Semi Annually", "90 day notice T+30", 120, "Lock up 2-year for invested capital"),
    ("Hedge Funds", "Synthetic Macro Fund", 30e6, "Liquid", "Monthly", "T+14", 41, None),
    ("Hedge Funds", "Synthetic Multi-Strategy", 25e6, "Liquid", "Quarterly", "T+60", 60, "Investor-level gate of 25% per quarter"),
    ("Hedge Funds", "Synthetic Relative Value", 20e6, "Liquid", "Quarterly", "T+60", 90, None),
    ("Real Estate", "Synthetic Core Property", 30e6, "Illiquid", "Quarterly", "T+10", 61, "30 days notice"),
    ("Private Debt", "Synthetic Distressed Debt", 15e6, "Illiquid", "Quarterly", "T+4", None, None),
    ("Infrastructure", "Synthetic Infrastructure II", 20e6, "Illiquid", "Illiquid until maturity / expiry ", "July 1st 2030", "+", None),
    ("Private Equity", "Synthetic Growth Co.", 10e6, "Illiquid", "Illiquid until maturity / expiry ", "-", "+", None),
    ("Real Estate", "Synthetic Tower (Land)", 50e6, "Illiquid", "Permenant illiquid holdings ", "-", "+", None),
    ("Real Estate", "Synthetic Bay Land", 15e6, "Illiquid", "Permenant illiquid holdings ", "-", "+", None),
]
RECEIVABLE = ("Cash & Equivalents", "Receivables", 12e6, "Illiquid", "Annually", None, 365, None)
AS_OF = dt.datetime(2030, 7, 31)


def _table(ws, rows):
    ws.append(HEADER)
    total = sum(r[2] for r in rows)
    for ac, name, v, lab, tl, pay, md, com in rows:
        ws.append([ac, name, v / total, v, lab, tl, pay, md, com, "Synthetic source"])
    ws.append(["Total", "AUM as of July '30", 1.0, total])
    return total


def write_liquidity_workbook(path: str | Path) -> dict:
    """Writes the workbook; returns the expected bucket values (USD) for tests."""
    wb = Workbook()
    es = wb.active
    es.title = "Estimates"
    es["E1"] = AS_OF
    es["D2"], es["E2"] = "Made-up estimates", sum(h[2] for h in HOLDINGS)

    _table(wb.create_sheet(TERMS_SHEET), HOLDINGS)
    _table(wb.create_sheet("Liquidity incl. Receivables"), HOLDINGS[:2] + [RECEIVABLE] + HOLDINGS[2:])

    expected = {"cash": 65e6, "immediate": 120e6, "short_term": 80e6 + 30e6, "monthly": 90e6 + 40e6, "st_quarterly": 30e6 + 25e6,
                "lt_quarterly": 20e6 + 30e6, "extended": 35e6, "maturity": 30e6, "permanent": 65e6, "unknown": 15e6}
    d = wb.create_sheet("Liquidity Dashboard")
    d["A1"], d["B1"] = "Portfolio Liquidity Summary ", sum(h[2] for h in HOLDINGS)
    d["A3"], d["B3"], d["C3"] = "Cash & Equivalents", "Cash Account", "Time Deposit"
    d["A4"], d["B4"], d["C4"] = 65e6, 40e6, 25e6
    d["A6"] = "Liquid Assets"
    for i, k in enumerate(["immediate", "short_term", "monthly", "st_quarterly"]):
        d.cell(7, 2 + i, expected[k])
    d["A9"] = "Illiquid Assets"
    for i, k in enumerate(["lt_quarterly", "extended", "maturity", "permanent"]):
        d.cell(10, 2 + i, expected[k] - (15e6 if k == "permanent" else 0))  # seeded fault: the last land row is left out
    wb.save(path)
    return expected


def sheet_rows(path: str | Path) -> dict[str, list]:
    """{sheet: rows[r][c]} with 1-based cached values and dates as Excel serials: the shape the website's reader gives."""
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows: list = [None] * (ws.max_row + 1)
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if v is None or v == "":
                    continue
                if isinstance(v, dt.datetime):
                    v = (v - dt.datetime(1899, 12, 30)).days
                rows[c.row] = rows[c.row] or [None] * (ws.max_column + 1)
                rows[c.row][c.column] = v
        out[ws.title] = rows
    return out
