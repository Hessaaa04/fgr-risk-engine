# Backlog

## Phase 0 (foundations), status
- [x] Repository, CI (lint, tests, secret scan), data-hygiene test
- [x] Agent definitions (`.claude/agents/`) and CLAUDE.md
- [x] riskcore seeded from v0.4.2 with parity tests (risk, active, factors, PCA, stress, Brinson)
- [x] Synthetic portfolio generator, workbook writer, seeded-error workbook
- [x] Desmoothing and uncertainty tools with tests
- [ ] Independent validation report for the ported models (model-validator)
- [ ] Data model design and plain-language data dictionary, approved by Hessa
- [ ] Web-filter test page opened on a work PC (spec Q2)

## Phase 1 (governed month-end)
- [ ] Pyodide runtime spike: run riskcore in the browser, measure load time
- [ ] Ingestion: template detection, validation rules (catch every seeded error), reconciliation
- [ ] Dataset file: encryption, versions, change log, sign-off, source fingerprints
- [ ] Flows and performance: TWR, IRR, value bridge incl. oil contributions
- [ ] Screens: holdings, allocation, cash and contributions, performance, core risk with labels
- [ ] Monthly report pack (PDF, Excel)

## Phase 2
- [ ] Port optimizer and signals; desmoothing and proxies wired into risk; lagged betas
