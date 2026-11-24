# How the engine's numbers are checked, standing process

The aim: nobody, human or agent, marks their own homework, and "is the number right?" is answered
by evidence that is rerun automatically, not by trust.

## Who checks what

| Role | Who | Checks | May change |
| --- | --- | --- | --- |
| Model builder | Build thread / quant-researcher and software-engineer agents | Writes and documents models | `riskcore/`, `docs/` |
| Model validator | Separate thread / `model-validator` agent | Is the maths right, and is the method fit for this portfolio? | `validation/`, `tests/parity/` |
| QA | `qa-engineer` agent | Does the software behave: edge cases, regressions, go / no-go | `tests/`, `e2e/` |
| Model owner | Hessa | Approves methodology and each validation verdict | Everything, by decision |

The builder never edits `validation/`; the validator never edits `riskcore/`.

## Four layers of evidence, each rerun on every change (CI)

1. **Independent recomputation** (`validation/test_reference_checks.py`): each formula recomputed by
   another route (integration, finite differences, optimiser, Monte Carlo, textbook case).
2. **Truth tests on synthetic data:** the generator knows each fund's true return and beta, so the
   engine can be scored against the right answer, not just against the old engine.
3. **Findings as tests** (`validation/test_findings.py`): every open finding is a test expected to
   fail. A fix makes it pass, CI flags the change, and the validator re-reviews before closing it.
4. **Parity** (`tests/parity/`): proves the port did not change v0.4.2's behaviour by accident.

## On real data (work PCs only, never this repository)

Each month-end, the engine runs automatic diagnostics and puts them in the report pack:
- VaR backtest: breaches against the expected count (Kupiec test), cumulated since go-live.
- Per fund: autocorrelation, share of zero months, valuation lag, filled share, beta significance.
- Reconciliation: values and flows tie to the management accounts.
- Changes: any figure that moved more than a set threshold since last month, with the reason.
Hessa (or a delegate) signs off the pack; the sign-off is recorded with the dataset version.

## When the validator is called
- Any change to `riskcore/` (before merge).
- Any new data source or valuation method.
- Once a year, a full review of every model in `docs/models/register.md`.

## What agents are and are not
The agents are Claude Code reviewers used while the software is built and changed. They do not run
inside the website and cannot see real data. Their output is a written verdict plus tests that keep
running; the approval decision stays with a person.
