# FGR Risk Engine

Portfolio risk and analytics engine for a multi-asset institutional portfolio, including
alternatives without Bloomberg coverage. This repository holds code and synthetic data only.

**Status: Phase 0 (foundations).** The calculation library reproduces the validated v0.4.2
engine; the website comes in Phase 1. See `docs/backlog.md`.

## What is here

| Folder | What it is |
| --- | --- |
| `riskcore/` | The calculations, in Python: volatility, VaR, Expected Shortfall, risk decomposition, active risk, factor betas, PCA, stress and reverse stress tests, Brinson attribution, desmoothing, uncertainty ranges |
| `synthetic/` | A generator for a realistic made-up portfolio (six asset classes, smoothed and stale-priced alternatives, oil contributions) and an Excel writer |
| `legacy/v0_4_2/` | The previous engine, frozen, used only to prove the new code gives the same answers |
| `tests/` | Unit, property, parity and data-hygiene tests |
| `docs/` | Architecture, decision log, model register, data rules, backlog |
| `.claude/agents/` | The AI development team's role definitions |

## Running it

```
pip install -r requirements-dev.txt
python -m pytest -q                     # all tests (parity tests need Node.js)
python scripts/make_synthetic.py        # writes synthetic workbooks to out/
```

## Rules

No real portfolio data in this repository, ever. See `CLAUDE.md` and `docs/data-rules.md`.

## The test website

`python scripts/build_web.py dist/ --csp` builds the site into `dist/` (code and made-up sample data only).
Serve that folder with any static web server, for example `python -m http.server -d dist`, and open it in Chrome or Edge.
Excel files loaded on the Data page are read inside the browser tab; nothing is uploaded or saved.
