# Data rules

1. **Real data never enters this repository**, the website host or shared cloud folders.
   It stays on work PCs and the shared drive. `.gitignore` blocks spreadsheet and data files,
   and `tests/test_repo_hygiene.py` fails CI if one is committed.
2. **Development uses synthetic data only** (`synthetic/`). Every synthetic name starts with
   "Synthetic". The generator is seeded, so the same seed always gives the same portfolio.
3. **Missing is missing.** `None`, never 0. Any fill, proxy or correction is recorded as lineage
   (`riskcore.estimation.Lineage`) and reported beside the figures it affects.
4. **Data domains stay separate:** reference, holdings, valuations, returns, cash flows
   (oil contributions, withdrawals, subscriptions, redemptions, transfers), cash balances,
   market data, benchmarks. A cash flow is never inferred from a change in value.
5. **Oil contributions are external flows**: excluded from time-weighted returns, included in
   money-weighted returns, liquidity and the value bridge.

## Synthetic workbook

`python scripts/make_synthetic.py` writes to `out/` (git-ignored):

- `synthetic-portfolio.xlsx`: sheets Read me, Instruments, Valuations, Flows, Market data.
- `synthetic-portfolio-with-errors.xlsx` plus `.errors.json`: the same data with six seeded
  errors (repeated month, value in thousands, missing return, unknown instrument, duplicate row,
  outlier return), each with its Excel row and the validation rule that should catch it.
