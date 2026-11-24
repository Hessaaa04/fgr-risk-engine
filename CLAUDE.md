# FGR Risk Engine: rules for Claude Code

This repository holds the code for an institutional portfolio risk and analytics engine.
The authoritative specification is the Master Project Specification (Claude Doc); its
decisions are mirrored in `docs/decision-log.md`.

## Non-negotiable rules

1. **No real portfolio data in this repository, ever.** No holdings, units, values, flows,
   manager terms or fund names from the real portfolio. Use `synthetic/` only. Real data is
   opened by users in their browser on work PCs and never leaves them.
2. **Never invent missing data silently.** Missing is `None`, never zero. Any fill, proxy or
   correction must be recorded as lineage on the figures it affects.
3. **Do not present unreliable estimates as precise.** Risk figures carry a confidence label;
   headline measures carry a range (`riskcore/uncertainty.py`).
4. **The model builder never validates its own model.** Changes to `riskcore/` need the
   model-validator agent's review and Hessa's approval before merge.
5. **Preserve working behaviour.** `tests/parity/` proves riskcore reproduces v0.4.2. A change
   that breaks parity must be intended, explained in the PR and logged in the decision log.

## Layout

- `riskcore/` pure calculation library: no file, network or database access.
- `synthetic/` deterministic synthetic portfolio generator and workbook writer.
- `legacy/v0_4_2/engine.js` the frozen v0.4.2 engine, used only as the parity oracle.
- `tests/` unit, property, parity and repository-hygiene tests.
- `docs/` architecture, decision log, model register, data rules, backlog.
- `.claude/agents/` the development team's subagent definitions.

## Working conventions

- Run `ruff check .` and `python -m pytest -q` before every commit.
- Returns are decimals per month; "_a" or "A" means annualised by sqrt(12); VaR/ES are positive losses.
- Explain consequential decisions in plain language in the PR description; Hessa has a finance
  background and limited programming experience.
