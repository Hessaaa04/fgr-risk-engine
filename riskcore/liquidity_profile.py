"""Liquidity profile: how much of the portfolio can be turned into cash, and how fast.

Follows the buckets of FGR's monthly liquidity report, but assigns every holding from its own
terms (redemption timeline and maximum days to cash) instead of from hand-picked cell lists:

    cash            cash accounts and time deposits (principal only)
    immediate       1 to 5 days            liquid
    short_term      6 to 15 days           liquid
    monthly         16 to 40 days          liquid
    st_quarterly    41 to 60 days          liquid
    lt_quarterly    more than 60 days      illiquid
    extended        semi-annual or annual  illiquid
    maturity        illiquid until maturity / expiry
    permanent       permanent illiquid holdings
    unknown         terms missing: shown, never guessed

"Max days" is taken as given in the report and treated as the worst case from the decision to
sell until cash arrives (notice, wait for the dealing date and settlement). Nothing is added to it.

Gates, lock-ups and redemption fees exist in the report only as free text. They are applied only
when an analyst enters them (Terms); a comment that mentions one without an entry is flagged, never
read as "no gate". Missing values stay None and are reported; nothing is filled in.
"""

from __future__ import annotations

import datetime as _dt
import re as _re
from dataclasses import dataclass, field

BUCKETS = [
    ("cash", "Cash & equivalents", "cash"),
    ("immediate", "Immediate (1–5 days)", "liquid"),
    ("short_term", "Short-term (6–15 days)", "liquid"),
    ("monthly", "Monthly (16–40 days)", "liquid"),
    ("st_quarterly", "Short-term quarterly (41–60 days)", "liquid"),
    ("lt_quarterly", "Long-term quarterly (over 60 days)", "illiquid"),
    ("extended", "Extended (semi-annual or annual)", "illiquid"),
    ("maturity", "Until maturity or expiry", "illiquid"),
    ("permanent", "Permanent illiquid holdings", "illiquid"),
    ("unknown", "Terms missing", "unknown"),
]
KIND = {k: kind for k, _, kind in BUCKETS}
NAME = {k: n for k, n, _ in BUCKETS}
LADDER_DAYS = [1, 5, 15, 40, 60, 90, 180, 365]
LIQUID_MAX_DAYS = 60
PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 91, "semi": 182, "annual": 365}
_MENTION = _re.compile(r"\b(gate|gated|gating|lock[- ]?up|suspen\w*|side[- ]?pocket|redemption (charge|fee)|fee of)\b", _re.I)


@dataclass
class Terms:
    """Analyst-entered terms for one holding. None means not entered."""
    gate: float | None = None  # share of the holding that can leave per dealing date, e.g. 0.25
    lockup_end: str | None = None  # ISO date before which nothing can be redeemed
    fee: float | None = None  # redemption fee as a share of value


@dataclass
class Position:
    name: str
    asset_class: str | None
    value: float | None
    label: str | None = None  # the report's own Liquid / Illiquid label, normalised to lower case
    timeline: str | None = None
    max_days: float | None = None  # None when missing; no_redemption marks "+" (no redemption right)
    no_redemption: bool = False
    payment: str | None = None
    comments: str | None = None
    source: str | None = None
    raw_label: str | None = None


@dataclass
class Profile:
    as_of: str | None
    positions: list[Position]
    total_reported: float | None = None  # the report's own AUM row, for reconciliation
    reported_buckets: dict[str, float] = field(default_factory=dict)  # the report's own dashboard figures


def _t(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def bucket(p: Position) -> str:
    t = _t(p.timeline)
    if "permanent" in t or "permenant" in t:
        return "permanent"
    if "maturity" in t or "expiry" in t:
        return "maturity"
    if "semi" in t or "annual" in t:
        return "extended"
    if _t(p.asset_class).startswith("cash"):
        return "cash"
    d = p.max_days
    if d is None:
        return "maturity" if p.no_redemption else "unknown"
    if d <= 5:
        return "immediate"
    if d <= 15:
        return "short_term"
    if d <= 40:
        return "monthly"
    if d <= LIQUID_MAX_DAYS:
        return "st_quarterly"
    return "lt_quarterly"


def period_days(timeline: str | None) -> int | None:
    t = _t(timeline)
    for k, d in PERIOD_DAYS.items():
        if k in t:
            return d
    return None


def _days_between(a: str | None, b: str | None) -> int | None:
    try:
        return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def available(r: dict, d: int, terms: Terms | None, as_of: str | None, suspend: float = 0.0) -> float:
    """Value that can be in cash within d days: contractual terms, entered gates/lock-ups/fees, and an optional
    suspension of a share of quarterly-or-longer funds (stressed view)."""
    v, md = r["value"], r["max_days"]
    if v is None or md is None or r["bucket"] in ("maturity", "permanent", "unknown") or d < md:
        return 0.0
    frac = 1.0
    if terms is not None:
        lock = _days_between(as_of, terms.lockup_end)
        if lock is not None and lock > d:
            return 0.0
        if terms.gate is not None and terms.gate > 0:
            per = period_days(r["timeline"]) or 30
            frac = min(1.0, (1 + (d - md) // per) * terms.gate)
        if terms.fee:
            frac *= 1 - terms.fee
    if suspend and (period_days(r["timeline"]) or 0) >= 91:
        frac *= 1 - suspend
    return v * frac


def analyse(pr: Profile, min_liquid: float = 0.75, horizon: int = LIQUID_MAX_DAYS, terms: dict[str, Terms] | None = None,
            suspend_quarterly: float = 0.0) -> dict:
    """Buckets, days-to-cash ladder (contractual and stressed), limit check and data checks for one month's report.

    The limit is "at least min_liquid of AUM can be in cash within horizon days" (contractual terms; with
    entered gates and lock-ups). Holdings with missing terms count as not available."""
    terms = terms or {}
    rows, checks = [], []
    valued = [p for p in pr.positions if p.value is not None]
    aum = sum(p.value for p in valued)
    for p in pr.positions:
        b = bucket(p)
        rows.append({
            "name": p.name, "asset_class": p.asset_class, "value": p.value,
            "w": p.value / aum if (p.value is not None and aum) else None,
            "bucket": b, "kind": KIND[b], "label": p.label, "timeline": p.timeline,
            "max_days": p.max_days, "no_redemption": p.no_redemption, "payment": p.payment,
            "comments": p.comments, "source": p.source,
        })
        if p.value is None:
            checks.append({"level": "error", "name": p.name, "text": "has no valuation, so it is left out of every total (not counted as zero)."})
        if b == "unknown":
            checks.append({"level": "error", "name": p.name, "text": "has no maximum days to cash and no timeline that places it, so it is not in any bucket."})
        if p.label in ("liquid", "illiquid") and KIND[b] in ("liquid", "illiquid") and p.label != KIND[b]:
            why = f"{p.max_days:g} days to cash" if p.max_days is not None else f"timeline “{p.timeline}”"
            checks.append({"level": "warn", "name": p.name,
                           "text": f"is labelled {p.label.title()} in the report, but its terms ({why}) put it in “{NAME[b]}”, which counts as {KIND[b]}."})
        if p.comments and _MENTION.search(p.comments) and p.name not in terms:
            checks.append({"level": "warn", "name": p.name,
                           "text": f"has a comment that mentions a gate, lock-up, suspension or fee (“{p.comments[:90]}”), "
                                   "but no terms are entered, so none is applied. Enter them on the Liquidity page."})
        if p.raw_label is not None and p.raw_label != p.raw_label.strip():
            checks.append({"level": "info", "name": p.name,
                           "text": f"has extra spaces in its label (“{p.raw_label}”). Excel formulas that look for exactly “{p.raw_label.strip()}” skip it."})

    by = {k: sum(r["value"] for r in rows if r["bucket"] == k and r["value"] is not None) for k, _, _ in BUCKETS}
    share = {k: (v / aum if aum else None) for k, v in by.items()}
    cash = share["cash"] or 0.0
    liquid = sum(share[k] or 0.0 for k, _, kind in BUCKETS if kind == "liquid")
    illiquid = sum(share[k] or 0.0 for k, _, kind in BUCKETS if kind == "illiquid")
    days = sorted(set(LADDER_DAYS + [horizon]))
    ladder = []
    for d in days:
        v = sum(available(r, d, None, pr.as_of) for r in rows)
        g = sum(available(r, d, terms.get(r["name"]), pr.as_of) for r in rows)
        s = sum(available(r, d, terms.get(r["name"]), pr.as_of, suspend_quarterly) for r in rows)
        ladder.append({"days": d, "value": v, "share": v / aum if aum else None,
                       "with_terms": g, "with_terms_share": g / aum if aum else None,
                       "stressed": s, "stressed_share": s / aum if aum else None})
    at_h = next(x for x in ladder if x["days"] == horizon)

    recon = []
    if pr.total_reported is not None and aum:
        diff = aum - pr.total_reported
        recon.append({"item": "Total AUM", "engine": aum, "report": pr.total_reported, "diff": diff, "diff_share": diff / aum})
    for k, v in pr.reported_buckets.items():
        if k in by and aum:
            recon.append({"item": NAME[k], "bucket": k, "engine": by[k], "report": v,
                          "diff": by[k] - v, "diff_share": (by[k] - v) / aum})
    for r in recon:
        if abs(r["diff_share"]) >= 0.0005:
            checks.append({"level": "warn", "name": r["item"],
                           "text": f"differs from the report's own figure by {r['diff_share']:+.2%} of AUM. "
                                   "The engine adds up every holding's terms; the report may have missed a row."})

    return {
        "as_of": pr.as_of, "aum": aum, "rows": rows, "buckets": [
            {"key": k, "name": n, "kind": kind, "value": by[k], "share": share[k]} for k, n, kind in BUCKETS if k != "unknown" or by[k]
        ],
        "cash": cash, "liquid": liquid, "liquid_incl_cash": liquid + cash, "illiquid": illiquid,
        "unknown": share["unknown"] or 0.0, "illiquid_for_limits": illiquid + (share["unknown"] or 0.0),
        "limit": {"min_liquid": min_liquid, "horizon": horizon, "available": at_h["with_terms_share"],
                  "ok": at_h["with_terms_share"] is not None and at_h["with_terms_share"] >= min_liquid,
                  "headroom": None if at_h["with_terms_share"] is None else at_h["with_terms_share"] - min_liquid,
                  "stressed": at_h["stressed_share"],
                  "stressed_ok": at_h["stressed_share"] is not None and at_h["stressed_share"] >= min_liquid},
        "suspend_quarterly": suspend_quarterly,
        "terms_entered": sorted(n for n in terms if any(r["name"] == n for r in rows)),
        "not_captured": ["Unfunded commitments and expected capital calls are not in the liquidity report, so they are not deducted."],
        "ladder": ladder, "reconciliation": recon, "checks": checks,
        "n_missing_value": sum(1 for p in pr.positions if p.value is None),
    }


def compare(a: dict, b: dict) -> list[dict]:
    """Holding-level change between two analysed months (a earlier, b later), matched by name."""
    pa = {r["name"]: r for r in a["rows"]}
    out = []
    for r in b["rows"]:
        o = pa.get(r["name"])
        out.append({"name": r["name"], "before": o["value"] if o else None, "after": r["value"],
                    "bucket_before": o["bucket"] if o else None, "bucket_after": r["bucket"],
                    "moved": bool(o) and o["bucket"] != r["bucket"], "new": o is None})
    names = {r["name"] for r in b["rows"]}
    out += [{"name": n, "before": o["value"], "after": None, "bucket_before": o["bucket"], "bucket_after": None,
             "moved": False, "new": False, "gone": True} for n, o in pa.items() if n not in names]
    return out
