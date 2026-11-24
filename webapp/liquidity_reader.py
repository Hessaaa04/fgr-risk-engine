"""Read FGR's monthly liquidity report (the "Liquidity Profile" workbook) from sheet cells.

The website reads the workbook with legacy/v0_4_2/xlsx.js and passes {sheet name: rows}, where
rows[r][c] are 1-based cached cell values (number, text, or null). Layout, as in the July 2026 report:

- "Portfolio Liq. Terms & NAV": one row per holding under a header row with Asset Class, Name,
  Allocation, Valuations, Liquidity, Timeline, PMT of Proceeds, Max Days, Comments, Source; a "Total"
  row ends the table. Max Days is a number, or "+" for no redemption right.
- "Liquidity incl. Receivables": the same table with a receivables row (optional).
- "Liquidity Dashboard": the report's own bucket figures, used only to reconcile against.
- "Estimates": the report date in E1.
"""

from __future__ import annotations

import datetime as dt
import re

from riskcore.liquidity_profile import Position, Profile

COLS = {
    "asset_class": r"^asset\s*class", "name": r"^name$", "value": r"^valuation", "label": r"^liquidity$",
    "timeline": r"^timeline", "payment": r"^pmt|^payment", "max_days": r"^max\s*days", "comments": r"^comment", "source": r"^source",
}


def _s(v) -> str:
    return " ".join(str(v).split()) if isinstance(v, str) else ""


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cell(rows, r, c):
    row = rows[r] if 0 <= r < len(rows) and rows[r] else None
    return row[c] if row and 0 <= c < len(row) else None


def _serial(v) -> str | None:
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return v[:10]
    return None


def find_sheet(names: list[str], kind: str) -> str | None:
    for n in names:
        t = _s(n).lower()
        if kind == "terms" and "terms" in t and "liq" in t:
            return n
        if kind == "receivables" and "receivable" in t and "dashboard" not in t:
            return n
        if kind == "dashboard" and "dashboard" in t and "rec" not in t:
            return n
        if kind == "estimates" and t.startswith("estimate"):
            return n
    return None


def read_table(rows: list) -> tuple[list[Position], float | None, list[dict]]:
    issues: list[dict] = []
    hdr_r, cols = None, {}
    for r in range(1, min(len(rows), 15)):
        found = {}
        for c in range(1, len(rows[r] or [])):
            h = _s(_cell(rows, r, c)).lower()
            for k, pat in COLS.items():
                if k not in found and re.search(pat, h):
                    found[k] = c
        if "name" in found and "max_days" in found:
            hdr_r, cols = r, found
            break
    if hdr_r is None:
        raise ValueError("no header row with “Name” and “Max Days” was found")
    for k in ("value", "label", "timeline"):
        if k not in cols:
            issues.append({"level": "warn", "text": f"no “{k.replace('_', ' ')}” column was found; that information is treated as missing."})
    out, total = [], None
    for r in range(hdr_r + 1, len(rows)):
        first = _s(_cell(rows, r, 1)).lower()
        name = _s(_cell(rows, r, cols["name"]))
        if first == "total":
            total = _num(_cell(rows, r, cols["value"])) if "value" in cols else None
            break
        if not name:
            continue
        g = (lambda k, r=r: _cell(rows, r, cols[k]) if k in cols else None)  # noqa: E731
        md = g("max_days")
        raw_label = g("label") if isinstance(g("label"), str) else None
        out.append(Position(
            name=name, asset_class=_s(g("asset_class")) or None, value=_num(g("value")),
            label=_s(raw_label).lower() or None, raw_label=raw_label, timeline=_s(g("timeline")) or None,
            max_days=_num(md), no_redemption=isinstance(md, str) and md.strip() == "+",
            payment=_s(g("payment")) or None if g("payment") not in ("-", None) else None,
            comments=(_s(g("comments")) or None) if _s(g("comments")) not in ("", "-") else None,
            source=_s(g("source")) or None,
        ))
    return out, total, issues


def read_dashboard(rows: list) -> dict[str, float]:
    """The report's own figures for each bucket (values in USD). Best effort: an empty dict if the layout differs."""
    got: dict[str, float] = {}
    keys = {"Liquid Assets": ["immediate", "short_term", "monthly", "st_quarterly"],
            "Illiquid Assets": ["lt_quarterly", "extended", "maturity", "permanent"]}
    for r in range(1, min(len(rows), 30)):
        a = _s(_cell(rows, r, 1))
        if a in keys:
            for i, k in enumerate(keys[a]):
                v = _num(_cell(rows, r + 1, 2 + i))
                if v is not None:
                    got[k] = v
        if a.startswith("Cash & Equivalents") and _num(_cell(rows, r + 1, 1)) is not None and "cash" not in got:
            got["cash"] = _num(_cell(rows, r + 1, 1))
    return got


def read_report(sheets: dict[str, list], file: str = "", receivables: bool = False) -> tuple[Profile, list[dict]]:
    names = list(sheets)
    issues: list[dict] = []
    ts = find_sheet(names, "receivables") if receivables else None
    if receivables and not ts:
        issues.append({"level": "warn", "text": f"{file}: no “incl. Receivables” sheet, so receivables are not included."})
    ts = ts or find_sheet(names, "terms")
    if not ts:
        raise ValueError("no “Portfolio Liq. Terms & NAV” sheet was found")
    pos, total, iss = read_table(sheets[ts])
    issues += [{"level": i["level"], "text": f"{file} › {ts.strip()}: {i['text']}"} for i in iss]
    as_of = None
    es = find_sheet(names, "estimates")
    if es:
        for r in range(1, 4):
            for c in range(1, 8):
                as_of = as_of or _serial(_cell(sheets[es], r, c))
    if not as_of:
        m = re.search(r"([A-Z][a-z]+)\s*'?(\d{2})", " ".join(_s(_cell(sheets[ts], r, 2)) for r in range(1, len(sheets[ts]))))
        issues.append({"level": "info", "text": f"{file}: no report date found in “Estimates”" + (f"; using “{m.group(0)}” from the total row." if m else ".")})
        as_of = m.group(0) if m else None
    dash = find_sheet(names, "dashboard")
    reported = read_dashboard(sheets[dash]) if (dash and not receivables) else {}
    return Profile(as_of=as_of, positions=pos, total_reported=total, reported_buckets=reported), issues
