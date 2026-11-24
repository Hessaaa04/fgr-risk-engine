"""Generate a synthetic multi-asset portfolio shaped like the institution's own.

Shape (not content) copied from the real portfolio:
  - six sleeves: Equities, Fixed Income, Alternative, Global Multi-Asset,
    Strategic Investments, Cash & Equivalents
  - three valuation methods: market price x units, entered return, entered value
  - smoothed hedge funds, annually revalued property and strategic holdings,
    a quarterly-valued private equity fund
  - monthly oil contributions into cash, occasional transfers out, rebalancing,
    funds opened and closed part-way through the history
  - five market factors, two benchmarks, one bond index

Outputs are deterministic for a given seed. True (unsmoothed) returns are kept
so tests can check that desmoothing recovers them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from riskcore.calendar import ym_add, ym_range
from riskcore.smoothing import smooth

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 20261124
FIRST_VALUE_MONTH = "2015-08"  # opening values only
FIRST_RETURN_MONTH = "2015-09"
LAST_MONTH = "2026-10"

SLEEVES = ["Equities", "Fixed Income", "Alternative", "Global Multi-Asset", "Strategic Investments", "Cash & Equivalents"]

# name, ticker, mean monthly return, monthly vol
FACTORS = [
    ("Global equities", "SYN-EQ", 0.0065, 0.044),
    ("US Treasuries", "SYN-UST", 0.0018, 0.014),
    ("High yield credit", "SYN-HY", 0.0045, 0.022),
    ("US dollar", "SYN-USD", 0.0005, 0.019),
    ("Oil", "SYN-OIL", 0.0030, 0.090),
]
FACTOR_CORR = np.array(
    [
        [1.00, -0.25, 0.70, -0.30, 0.35],
        [-0.25, 1.00, 0.05, 0.10, -0.15],
        [0.70, 0.05, 1.00, -0.30, 0.35],
        [-0.30, 0.10, -0.30, 1.00, -0.30],
        [0.35, -0.15, 0.35, -0.30, 1.00],
    ]
)
STUDENT_T_DF = 5  # fat tails


@dataclass
class InstrumentSpec:
    name: str
    sleeve: str
    method: str  # 'market_price' | 'entered_return' | 'entered_value'
    frequency: str  # 'monthly' | 'quarterly' | 'annual'
    liquid: bool
    notice_days: int
    betas: tuple[float, float, float, float, float]
    idio_vol: float
    alpha: float = 0.0
    smoothing_phi: float = 0.0
    start: str = FIRST_VALUE_MONTH
    end: str | None = None
    weight: float = 0.0  # share of opening portfolio (when start = FIRST_VALUE_MONTH)
    ticker: str = ""


def _specs() -> list[InstrumentSpec]:
    S = []
    eq = [  # name suffix, weight, betas(eq, ust, hy, usd, oil), idio
        ("Equity Fund A", 0.060, (1.00, 0.0, 0.0, -0.10, 0.0), 0.012),
        ("Equity Fund B", 0.050, (1.10, 0.0, 0.0, -0.05, 0.0), 0.020),
        ("Equity Fund C (Technology)", 0.035, (1.25, 0.0, 0.0, 0.0, 0.0), 0.030),
        ("Equity Fund D (Europe)", 0.035, (0.95, 0.0, 0.0, -0.40, 0.0), 0.018),
        ("Equity Fund E (Japan)", 0.030, (0.80, 0.0, 0.0, -0.30, 0.0), 0.025),
        ("Equity Fund F (Emerging)", 0.030, (1.15, 0.0, 0.1, -0.30, 0.10), 0.030),
        ("Equity Index Fund G", 0.045, (1.00, 0.0, 0.0, 0.0, 0.0), 0.004),
    ]
    for i, (n, wt, b, iv) in enumerate(eq):
        S.append(InstrumentSpec(f"Synthetic {n}", "Equities", "market_price", "monthly", True, 3, b, iv, weight=wt, ticker=f"SYNEQ{i + 1:02d}"))
    S.append(InstrumentSpec("Synthetic Equity Fund H (new 2023)", "Equities", "market_price", "monthly", True, 3,
                            (1.05, 0, 0, -0.1, 0), 0.020, start="2023-01", ticker="SYNEQ08"))
    S.append(InstrumentSpec("Synthetic Equity Fund J (closed 2021)", "Equities", "market_price", "monthly", True, 3,
                            (1.0, 0, 0, 0, 0), 0.020, weight=0.020, end="2021-06", ticker="SYNEQ09"))
    fi = [
        ("Bond Fund A (Global Aggregate)", 0.080, (0.0, 0.90, 0.10, 0.20, 0.0), 0.004, "market_price"),
        ("Bond Fund B (Credit)", 0.060, (0.10, 0.50, 0.45, 0.0, 0.0), 0.006, "market_price"),
        ("Bond Fund C (Emerging Debt)", 0.040, (0.20, 0.40, 0.60, -0.20, 0.05), 0.010, "market_price"),
        ("Bond Fund D (Short Duration)", 0.050, (0.0, 0.30, 0.10, 0.0, 0.0), 0.002, "entered_return"),
        ("Bond Fund E (Investment Grade)", 0.050, (0.05, 0.80, 0.20, 0.0, 0.0), 0.004, "entered_return"),
    ]
    for i, (n, wt, b, iv, m) in enumerate(fi):
        S.append(InstrumentSpec(f"Synthetic {n}", "Fixed Income", m, "monthly", True, 3, b, iv, weight=wt,
                                ticker=f"SYNFI{i + 1:02d}" if m == "market_price" else ""))
    S.append(InstrumentSpec("Synthetic Bond Fund F (new 2022)", "Fixed Income", "market_price", "monthly", True, 3,
                            (0.1, 0.6, 0.4, 0, 0), 0.006, start="2022-04", ticker="SYNFI06"))
    alt = [
        ("Hedge Fund A (Multi-Strategy)", 0.030, (0.25, 0.10, 0.15, 0.0, 0.0), 0.010, 0.25, "monthly", True, 95),
        ("Hedge Fund B (Macro)", 0.020, (0.10, 0.20, 0.0, 0.10, 0.05), 0.015, 0.20, "monthly", True, 65),
        ("Hedge Fund C (Credit)", 0.020, (0.15, 0.10, 0.50, 0.0, 0.0), 0.008, 0.45, "monthly", False, 180),
        ("Property Fund A", 0.025, (0.35, 0.20, 0.20, 0.0, 0.0), 0.015, 0.0, "annual", False, 365),
        ("Private Equity Fund A", 0.020, (1.20, 0.0, 0.20, 0.0, 0.0), 0.030, 0.55, "quarterly", False, 3650),
    ]
    for n, wt, b, iv, phi, fq, liq, nd in alt:
        S.append(InstrumentSpec(f"Synthetic {n}", "Alternative", "entered_value", fq, liq, nd, b, iv, smoothing_phi=phi, weight=wt))
    gma = [
        ("Multi-Asset Fund A", 0.040, (0.55, 0.35, 0.10, 0.0, 0.0), 0.006),
        ("Multi-Asset Fund B", 0.035, (0.45, 0.30, 0.20, -0.10, 0.0), 0.008),
    ]
    for i, (n, wt, b, iv) in enumerate(gma):
        S.append(InstrumentSpec(f"Synthetic {n}", "Global Multi-Asset", "market_price", "monthly", True, 5, b, iv, weight=wt, ticker=f"SYNMA{i + 1:02d}"))
    strat = [
        ("Strategic Holding A (Real Estate)", 0.060, (0.20, 0.0, 0.10, 0.0, 0.10), 0.012),
        ("Strategic Holding B (Land)", 0.040, (0.0, 0.0, 0.0, 0.0, 0.10), 0.010),
        ("Strategic Holding C (Private Company)", 0.020, (0.40, 0.0, 0.0, 0.0, 0.20), 0.025),
    ]
    for n, wt, b, iv in strat:
        S.append(InstrumentSpec(f"Synthetic {n}", "Strategic Investments", "entered_value", "annual", False, 3650, b, iv, weight=wt))
    S.append(InstrumentSpec("Synthetic Cash Account A (Operating)", "Cash & Equivalents", "entered_value", "monthly", True, 0, (0, 0, 0, 0, 0), 0.0, weight=0.050))
    S.append(InstrumentSpec("Synthetic Cash Account B (Deposits)", "Cash & Equivalents", "entered_value", "monthly", True, 30, (0, 0, 0, 0, 0), 0.0, weight=0.050))
    return S


@dataclass
class SyntheticPortfolio:
    seed: int
    months: list[str]  # all months incl. the opening-value month
    instruments: pd.DataFrame
    valuations: pd.DataFrame  # month, instrument, value, return (reported), true_return, status
    flows: pd.DataFrame  # month, date, type, instrument, amount, note
    market: pd.DataFrame  # index = month; columns = series names (returns)
    market_meta: pd.DataFrame  # name, type, ticker
    errors: list[dict] = field(default_factory=list)


def _factor_returns(rng: np.random.Generator, T: int) -> np.ndarray:
    vols = np.array([f[3] for f in FACTORS])
    means = np.array([f[2] for f in FACTORS])
    L = np.linalg.cholesky(FACTOR_CORR)
    z = rng.standard_t(STUDENT_T_DF, size=(T, len(FACTORS))) / np.sqrt(STUDENT_T_DF / (STUDENT_T_DF - 2))
    return means + (z @ L.T) * vols


def generate(seed: int = DEFAULT_SEED, opening_aum: float = 650e6) -> SyntheticPortfolio:
    rng = np.random.default_rng(seed)
    months = ym_range(FIRST_VALUE_MONTH, LAST_MONTH)
    rmonths = months[1:]
    T = len(rmonths)
    Fm = _factor_returns(rng, T)
    deposit = np.clip(0.0004 + np.cumsum(rng.normal(0, 0.00012, T)), 0.00005, 0.0045)

    specs = _specs()
    # true and reported returns per instrument
    true_r: dict[str, np.ndarray] = {}
    rep_r: dict[str, np.ndarray] = {}
    for sp in specs:
        if sp.sleeve == "Cash & Equivalents":
            tr = deposit * (1.0 if "Operating" in sp.name else 1.3)
        else:
            tr = sp.alpha + 0.0004 + Fm @ np.array(sp.betas) - (np.array(sp.betas) @ np.array([f[2] for f in FACTORS])) * 0.25 \
                + rng.normal(0, sp.idio_vol, T)
        true_r[sp.name] = tr
        obs = smooth(tr, sp.smoothing_phi) if sp.smoothing_phi > 0 else tr.copy()
        if sp.frequency == "annual":
            out = np.zeros(T)
            acc = 1.0
            for t, ym in enumerate(rmonths):
                acc *= 1 + tr[t]
                if ym[5:] == "12":
                    out[t] = acc - 1
                    acc = 1.0
            obs = out
            if "Land" in sp.name:  # some strategic holdings barely move at all
                obs = np.where(np.arange(T) % 24 == 15, obs, 0.0)
        elif sp.frequency == "quarterly":
            out = np.zeros(T)
            acc = 1.0
            for t, ym in enumerate(rmonths):
                acc *= 1 + obs[t]
                if ym[5:] in ("03", "06", "09", "12"):
                    out[t] = acc - 1
                    acc = 1.0
            obs = out
        rep_r[sp.name] = obs

    # values with flows: V_t = (V_{t-1} + F_t) * (1 + r_t)  (money added counts from the start of the month)
    names = [sp.name for sp in specs]
    spec_by = {sp.name: sp for sp in specs}
    V = {n: np.full(len(months), np.nan) for n in names}
    for sp in specs:
        if sp.start == FIRST_VALUE_MONTH:
            V[sp.name][0] = opening_aum * sp.weight
    flows = []
    cash_op = "Synthetic Cash Account A (Operating)"
    for t, ym in enumerate(rmonths, start=1):
        F = {n: 0.0 for n in names}
        # oil contribution into operating cash
        if rng.random() > 0.08:
            amt = round(float(rng.lognormal(np.log(3.0e6), 0.35)), -3)
            F[cash_op] += amt
            flows.append({"month": ym, "type": "oil_contribution", "instrument": cash_op, "amount": amt, "note": "Synthetic oil revenue contribution"})
        if ym in ("2020-04", "2020-05"):
            amt = -15e6
            F[cash_op] += amt
            flows.append({"month": ym, "type": "withdrawal", "instrument": cash_op, "amount": amt, "note": "Synthetic transfer out"})
        # fund opened / closed
        for sp in specs:
            if sp.start == ym:
                amt = 25e6
                F[sp.name] += amt
                F[cash_op] -= amt
                flows += [{"month": ym, "type": "subscription", "instrument": sp.name, "amount": amt, "note": "New investment"},
                          {"month": ym, "type": "transfer", "instrument": cash_op, "amount": -amt, "note": f"Paid to {sp.name}"}]
            if sp.end and ym_add(sp.end, 1) == ym:
                amt = V[sp.name][t - 1]
                F[sp.name] -= amt
                F[cash_op] += amt
                flows += [{"month": ym, "type": "redemption", "instrument": sp.name, "amount": -amt, "note": "Full redemption"},
                          {"month": ym, "type": "transfer", "instrument": cash_op, "amount": amt, "note": f"Received from {sp.name}"}]
        # quarterly rebalance: excess operating cash above 25m goes to equity and bond funds
        if ym[5:] in ("01", "04", "07", "10"):
            cash_now = V[cash_op][t - 1] + F[cash_op]
            excess = cash_now - 25e6
            if excess > 5e6:
                share = {"Equities": 0.40, "Fixed Income": 0.45, "Global Multi-Asset": 0.15}
                live = [sp for sp in specs if sp.sleeve in share and sp.method == "market_price"
                        and sp.start <= ym_add(ym, -1) and (sp.end is None or sp.end >= ym)]
                paid = 0.0
                for sl, sh in share.items():
                    grp = [sp.name for sp in live if sp.sleeve == sl]
                    each = round(excess * sh / len(grp), -3)
                    for n in grp:
                        F[n] += each
                        F[cash_op] -= each
                        paid += each
                        flows.append({"month": ym, "type": "subscription", "instrument": n, "amount": each, "note": "Rebalance from cash"})
                flows.append({"month": ym, "type": "transfer", "instrument": cash_op, "amount": -paid, "note": "Rebalance to funds"})
        for n in names:
            sp = spec_by[n]
            prev = V[n][t - 1]
            base = (0.0 if np.isnan(prev) else prev) + F[n]
            alive = sp.start <= ym and (sp.end is None or ym <= sp.end) and not (sp.start == ym and sp.start != FIRST_VALUE_MONTH and base == 0)
            if sp.end and ym_add(sp.end, 1) == ym:
                V[n][t] = 0.0
            elif alive and base > 0:
                V[n][t] = base * (1 + rep_r[n][t - 1])

    rows = []
    for n in names:
        sp = spec_by[n]
        for t, ym in enumerate(months):
            v = V[n][t]
            if np.isnan(v):
                continue
            if t == 0:
                rows.append({"month": ym, "instrument": n, "value": float(v), "return": None, "true_return": None, "status": "final"})
                continue
            first_month_new = sp.start == ym and sp.start != FIRST_VALUE_MONTH
            closed = v == 0.0
            r = None if first_month_new or closed else float(rep_r[n][t - 1])
            rows.append({"month": ym, "instrument": n, "value": float(v), "return": r,
                         "true_return": None if r is None else float(true_r[n][t - 1]),
                         "status": "final" if sp.method != "entered_value" or sp.frequency == "monthly" else "estimate"})
    valuations = pd.DataFrame(rows)

    instruments = pd.DataFrame(
        [{"instrument": sp.name, "sleeve": sp.sleeve, "valuation_method": sp.method, "valuation_frequency": sp.frequency,
          "liquid": sp.liquid, "notice_days": sp.notice_days, "ticker": sp.ticker, "currency": "USD",
          "first_month": sp.start, "last_month": sp.end or ""} for sp in specs]
    )

    mk = pd.DataFrame(Fm, index=rmonths, columns=[f[0] for f in FACTORS])
    gb = 0.85 * mk["US Treasuries"] - 0.25 * mk["US dollar"] + rng.normal(0, 0.003, T)
    mk["Global bonds (synthetic)"] = gb
    mk["50/50 reference (synthetic)"] = 0.5 * mk["Global equities"] + 0.5 * gb
    mk["Multi-asset 35 (synthetic)"] = 0.35 * mk["Global equities"] + 0.65 * gb - 0.0008
    meta = pd.DataFrame(
        [{"name": f[0], "type": "factor", "ticker": f[1]} for f in FACTORS]
        + [{"name": "Global bonds (synthetic)", "type": "index", "ticker": "SYN-GB"},
           {"name": "50/50 reference (synthetic)", "type": "benchmark", "ticker": "SYN-5050"},
           {"name": "Multi-asset 35 (synthetic)", "type": "benchmark", "ticker": "SYN-MA35"}]
    )
    fl = pd.DataFrame(flows)
    fl["date"] = fl["month"] + "-15"
    return SyntheticPortfolio(seed, months, instruments, valuations, fl[["month", "date", "type", "instrument", "amount", "note"]], mk, meta)
