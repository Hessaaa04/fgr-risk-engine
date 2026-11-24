# Independent validation: riskcore 0.1.0 (Phase 0 port of v0.4.2)

**Validator:** model-validator role (separate from the build thread). **Date:** 24 November 2026.
**Data:** synthetic portfolio only (`synthetic/generator.py`, seed 20261124, 26 live funds at Dec 2025).
**Evidence:** `validation/test_reference_checks.py` (14 independent recomputations, all pass) and
`validation/test_findings.py` (5 open findings written as tests that are expected to fail until fixed).

## Verdict

**Pass with conditions.** The arithmetic is right: every formula does what the methodology says,
confirmed by independent routes. The weaknesses are in the *inputs and assumptions*, mainly how
smoothed, stale and quarterly-valued funds are treated. On the synthetic portfolio, where the true
answer is known, the engine understates portfolio volatility by about 13% and stress losses by
10% to 40%, and gets the private equity fund's equity beta wrong in sign. Figures may be used
for development and parallel runs, not in an approved report, until V-01 to V-04 are fixed.

## 1. What is verified correct

Each figure was recomputed by a different method from the one riskcore uses.

| Calculation | Independent check | Result |
| --- | --- | --- |
| Portfolio volatility, covariance | Volatility of the rebuilt portfolio series | Exact |
| Parametric VaR and ES (normal) | Tail probability and numerical integration of the tail, at 90/95/99% | Exact (1e-8) |
| Historical VaR and ES | pandas quantile; order statistics | Exact |
| Maximum drawdown | pandas running-peak method | Exact |
| Marginal, component, incremental VaR; risk shares | Finite-difference derivatives; shares add to 100% and components to VaR | Exact (1e-6) |
| Tracking error, beta, correlation | Handover TE formula; scipy regression | Exact |
| Factor betas (OLS), portfolio beta | Normal equations; portfolio beta equals beta of the portfolio | Exact |
| PCA shares | Singular value decomposition | Exact |
| Stress propagation of unspecified factors | Monte Carlo: 400,000 simulated factor months | Within 0.4 pt |
| Reverse stress test | Numerical optimiser (SLSQP) | Within 1e-5 |
| Brinson-Fachler | Three-sector textbook case worked by hand | Exact |
| Carino linking | Linked effects add to the compounded excess over 24 months | Exact |
| Geltner desmoothing | Recovers the true series when the smoothing parameter is known | Exact |

## 2. Findings, most severe first

Severity: **High** = can materially mislead a decision, often silently. **Medium** = misleading in
some cases, or a weak assumption. **Low** = small or cosmetic.

### V-01 High. Smoothed and stale returns are used as reported, so risk is understated
Hedge, property, private equity and strategic holdings report smoothed or infrequent values.
riskcore has a desmoothing tool but does not use it anywhere in the analysis.

| Synthetic, Dec 2025, 36 months | Engine | True |
| --- | --- | --- |
| Portfolio volatility (annual) | 7.9% | 9.1% |
| Hedge Fund C (credit) volatility | 3.7% | 5.3% |
| Property Fund A volatility | 4.8% | 6.8% |
| Equities fall 20%: portfolio loss | 12.0% | 13.9% |
| Dollar rises 10%: portfolio loss | 1.9% | 3.2% |

The same bias runs through VaR, ES, the √12 annualisation (which assumes no autocorrelation),
correlations and risk shares. **Fix:** wire in desmoothing for flagged funds, estimate the smoothing
parameter on the full 2015+ history (see V-12), and label desmoothed figures.

### V-02 High. Quarterly-valued funds escape the stale flag
A fund valued quarterly shows a return in one month of three, so two thirds of its months are zero.
The stale rule needs 70%, so the private equity fund (66.4% zeros) is not flagged, and the
confidence label treats it as good reported data. **Fix:** classify by valuation frequency from the
instrument record, not by counting zeros; keep the zero count as a back-up check.

### V-03 High. Private equity and other lagged funds get wrong factor betas
Regressing a fund's return on the *same month's* market moves cannot see exposure that shows up a
quarter later. The synthetic private equity fund has a true equity beta of 1.2; the engine estimates
about −0.3, so an equity crash stress test shows it *gaining*. Adding lagged market returns
(Dimson method, lags 0 to 6, summed) gives 1.12; a quarterly regression gives 0.92.
**Fix:** lagged (Dimson) betas or quarterly regressions for lagged or smoothed funds, with a
documented beta floor or analyst override where history is too short.

### V-04 High. Unrecognised factor names give 0% stress shocks, silently
Preset and hypothetical scenarios look factors up by name ("globalequities", "oil" …). If the
workbook calls them anything else, every hypothetical scenario and the pre-2015 historical ones
show a 0.0% loss with no warning. **Fix:** map factors to fixed roles by ticker or an explicit
mapping, and refuse to run (with a clear message) when a scenario factor is not mapped.

### V-05 Medium. Brinson crashes on a valid setup
If an asset class has a benchmark weight but no index, attribution stops with an error
(the docstring says it should use the class's own return). It fails loudly, not wrongly.
**Fix:** use the stated rule, or reject the setup at entry with a message.

### V-06 High (practical). Liquidity is a single liquid/illiquid flag
No notice periods, redemption frequency, gates, lock-ups, or unfunded private-market commitments,
and no link to oil contribution inflows. The synthetic data already carries notice days; the
engine ignores them. For this portfolio, liquidity is a first-order risk. **Fix (Phase 1/2):** a
liquidity ladder (value available within 7, 30, 90, 365 days) from instrument terms, with
commitments and expected contributions as cash-flow lines.

### V-07 Medium. Tail figures from 36 months are very rough
With 36 months, 95% historical VaR lies between the 2nd and 3rd worst months and ES is the average
of the two worst; 99% is effectively the worst month. A block bootstrap gives a 90% range of
**1.7% to 3.9%** for a 95% historical VaR of 3.5%, and **6.6% to 9.2%** for 7.9% volatility.
The range tools exist (`uncertainty.py`) but are not shown yet. **Fix:** show ranges next to every
headline figure, and do not show 99% historical VaR on less than 100 months.

### V-08 Medium. A 36-month window describes a calm period
At December 2025 a 3-year window covers 2023 to 2025 and excludes 2020 and 2022. That is a fair
picture of *current* volatility but not of tail risk. **Recommendation:** use the rolling 36-month
("trailing three-year") window for headline volatility; full history from 2015 for historical VaR,
ES and smoothing estimates; and stress tests for events outside both.

### V-09 Medium. Up to 60% of a month can be filled in
The window keeps going back while only 40% of today's weight has its own data. Filled months copy
the asset-class average, which hides the fund's own risk. On the synthetic portfolio fills are
small (1% to 3% of cells), but the real portfolio may differ. Each fill is now recorded, which is good.
**Fix:** raise the default to about 70% and show the filled share beside the risk figures.

### V-10 Low to medium. Normal, zero-mean VaR
Backtest on synthetic data, 82 months (2019 to 2025): the 95% parametric VaR was breached 0 times
against about 4 expected (conservative); the historical VaR 5 times. 82 months cannot separate a
good model from a poor one with confidence. **Fix:** keep both, add a fat-tail adjustment
(Cornish-Fisher) as a comparison, and run the backtest monthly as a standing check.

### V-11 Medium. Factor betas need more months and error bars
Betas are computed with as few as 8 months for 5 factors, and no standard errors are shown.
**Fix:** require at least 24 months (36 preferred) and show which betas are statistically
distinguishable from zero.

### V-12 Medium. The smoothing estimate is itself noisy
Simulated fund with true smoothing 0.45: on 36 months the estimate averages 0.37 (90% range 0.12
to 0.59); on 120 months, 0.43 (0.29 to 0.55). Use the longest clean history, not the risk window.

### V-13 Needs checking in ingestion. Contributions and capital calls must not become returns
riskcore takes returns as given. For entered-value funds, returns come from value changes in the
workbooks; a capital call, distribution or oil contribution that is not stripped out becomes a
false gain or loss. This must be enforced and tested in the Phase 1 ingestion.

### V-14 Question. Currency
riskcore has no currency field; the synthetic portfolio is all USD. If any holding is valued in
another currency, FX translation and FX risk need a decision.

### V-15 Low. Stress presets are unsourced
The preset moves are consistent with the market history I know (for example global equities
about −20% in Feb to Mar 2020 and −25% in Jan to Sep 2022; the dollar about +17% in 2022), but they
have no recorded source or date. 2008 and 2011 always use presets because data starts in 2015.
Record a source for each.

### V-16 Low. Small conventions
Up to 2% of weight without a return counts as 0% in the portfolio return (it is not reweighted);
the "complete month" check uses the previous *listed* month, the return uses the previous
*calendar* month (same answer unless a month is missing). Historical scenario "actual" figures
compare today's portfolio estimate with the portfolio held at the time.

## 3. Conditions for "Pass"
1. V-01 to V-04 fixed, and their tests in `validation/test_findings.py` passing.
2. Ranges shown beside headline figures (V-07).
3. Ingestion tests for flows (V-13) before real data is loaded.
4. Hessa decides V-14 and the window policy (V-08).
