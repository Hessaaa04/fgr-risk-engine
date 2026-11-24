# Model register

Status of each calculation in `riskcore/`. "Parity" = reproduces the frozen v0.4.2 engine on
synthetic data in CI (`tests/parity/`). Independent validation by the model-validator agent is
still required before any figure appears in an approved report.
First independent validation: `validation/riskcore-0.1.0.md` (Pass with conditions, 24 Nov 2026).

| Model | Module | Source | Parity tolerance | Validation | Main limitation |
| --- | --- | --- | --- | --- | --- |
| Complete months, estimation window, return matrix with lineage | `estimation` | Port + lineage (new) | exact (1e-12) | Pending | Gap-filling from peers is an assumption; now recorded per cell |
| Volatility, parametric VaR/ES, historical VaR/ES, drawdown | `risk` | Port | 1e-8 | Pending | Normal assumption; 60 months gives wide error bands |
| Risk contribution, marginal, component, incremental VaR | `risk` | Port | 1e-8 | Pending | Understated for stale-priced holdings |
| Tracking error, beta, information ratio | `active` | Port | 1e-10 | Pending | Benchmark choice drives the result |
| Factor betas (OLS, 5 factors), PCA | `factors` | Port | 1e-8 | Pending | Betas biased to zero for smoothed returns |
| Stress, conditional propagation, reverse stress | `stress` | Port | 1e-9 | Pending | Systematic part only; no fund-specific shocks |
| Brinson-Fachler with Carino linking | `attribution` | Port | 1e-12 | Pending | Sleeve level only |
| Geltner desmoothing | `smoothing` | New | n/a | Pending | phi estimated with error (about +/-0.05 with 240 months) |
| Bootstrap ranges, confidence label | `uncertainty` | New | n/a | Pending | Label thresholds are a judgement; review with risk owner |
| Optimizer, signals | not yet ported | Phase 2 | | | |
