# Re-review: illiquid-fund corrections (PR #4, commit 4366503)

**Validator:** model-validator role. **Date:** 24 November 2026. **Data:** synthetic only.
**Verdict: Pass with conditions.** V-01 to V-05 are fixed; their tests now pass and are kept as
regression tests. Two new findings (V-17, V-18) are open as `xfail` tests.

## Before and after (synthetic portfolio, Dec 2025, 36-month window)

| Figure | v0.4.2 method | After PR #4 | True |
| --- | --- | --- | --- |
| Portfolio volatility | 7.9% | 8.7% | 9.1% |
| Equities fall 20%: loss | 12.0% | 13.4% | 13.9% |
| Dollar rises 10%: loss | 1.9% | 2.7% | 3.2% |
| Private equity equity beta | -0.27 | 1.10 | 1.20 |
| Hedge Fund C volatility | 3.7% | 4.9% | 5.3% |
| Confidence label | Medium | Medium (9.5% of cells modelled) | |

Checked independently: Euler contributions still add to VaR exactly with the added idiosyncratic
variance; the desmoothing is not applied to cash or equity funds; only funds flagged by the data
are changed, and each change is listed in `adjustments` with its lineage.

## Conditions and open items
- **V-17 (Medium).** Name patterns can give two factors the same role (e.g. "Global equities" and
  "EM equities", or Brent and WTI); both then take the full scenario move. Fix: a role filled by
  more than one factor must come from the explicit map, otherwise the scenario reports an error.
- **V-18 (Medium).** Private equity volatility is 15.7% modelled vs 19.9% true. The quarterly residual
  comes from still-smoothed quarterly returns, so the fund-specific part is too small. Options:
  desmooth the quarterly residuals (AR(1) at quarterly frequency) or set a documented floor.
- **Yearly-valued holdings (6.3% of the synthetic portfolio)** keep their reported returns and are
  flagged "needs an assumed beta or proxy". This is the right behaviour; Hessa needs to supply
  the assumed betas or proxies (open question in the validation report).
- Historical VaR excludes the added idiosyncratic variance: keep the label beside it.

## Follow-up re-review (commit 8e48d2f)
- **V-17 closed.** Colliding pattern matches lose the role unless set in `factor_map`; an exact role
  name keeps it; affected scenarios report an error. Checked with equities and oil collisions.
- **V-18 accepted as a Low limitation.** The variance-ratio and autocorrelation formulas for monthly
  AR(1) smoothing summed to quarters were checked against 200,000 simulated quarters at phi 0.3, 0.5
  and 0.7 (match to 3 decimals; the inversion recovers phi within 0.004). Modelled PE volatility is
  16.8% vs 19.9% true. The remaining gap comes from the beta (1.10 vs 1.20) and the credit exposure
  left out by the parsimony rule, which stays: 40 quarters cannot support a second factor. The 0.5
  floor (D25) is an assumption within the published 0.4 to 0.7 range and should be confirmed by
  Hessa. The test stays as `xfail` to track the gap and must not be passed by tuning the floor.
