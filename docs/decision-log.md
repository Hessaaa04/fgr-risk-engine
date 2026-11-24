# Decision log

Mirrors Section 12 of the Master Project Specification. Newest decisions at the bottom.

| # | Decision | Status | Reason |
| --- | --- | --- | --- |
| D1 | Excel remains the data-entry layer; Bloomberg feeds the workbooks on a licensed terminal | Carried from v0.4.2 | Team workflow and licensing |
| D2 | Management accounts are the source of truth for history | Carried | More accurate than yearly workbooks |
| D3 | Holdings are valued (units x price or entered value) and returns derived | Carried | Matches the team's valuation sheets |
| D4 | 50/50 reference is the risk benchmark; Multi-Asset 35 is the performance benchmark | Carried, to confirm | Earlier agreement |
| D5 | Real data is authorised (CEO) but never enters this repository, the website host or shared cloud folders | Agreed 24 Nov 2026 | Authorisation covers use, not storage location |
| D6 | Stage 1: private website, Python maths run in the browser (WebAssembly), data in encrypted dataset files on work PCs and the shared drive. Stage 2 adds a server on organisation-owned hosting | Agreed 24 Nov 2026 | Works on locked-down PCs without IT; same Python maths serves both stages |
| D7 | Append-only versions; corrections are new versions | Proposed | Reproducibility and audit |
| D8 | v0.4.2 stays in use, frozen, until v2 reaches parity and runs two parallel month-ends | Proposed | No gap in capability |
| D9 | MVP is a governed month-end with core risk; advanced analytics in Phase 2 | Proposed | Goal is more than a dashboard over Excel |
| D10 | Every risk figure carries a confidence label; headline measures a range | Proposed | No false precision |
| D11 | Model builder and validator are separate agents; Hessa approves methodology changes | Proposed | Independent validation |
| D12 | A desktop version, if ever needed, wraps the web front end | Proposed | One code base |
| D13 | No IT involvement for now | Agreed 24 Nov 2026 | Avoid bureaucracy while Stage 1 suffices |
| D14 | Code in a private repository on Hessa's GitHub account | Agreed 24 Nov 2026 | Hessa's choice; revisit at team rollout |
| D15 | riskcore is checked against the frozen v0.4.2 engine on synthetic data in every CI run | Phase 0, 24 Nov 2026 | Proves the port preserved validated behaviour |
| D16 | The confidence label also counts weight in stale-priced holdings (>5% caps it at Medium, >25% at Low) | Phase 0, 24 Nov 2026 | Stale holdings are "reported" data yet understate risk |
| D17 | Default risk window is a rolling 36 months (3 years); 60 and 120 remain options | Agreed 24 Nov 2026 (Hessa) | History runs 2015 to 2025; Hessa asked for a 3-year engine |
| D18 | The test website reads the same two workbooks as v0.4.2 with the frozen v0.4.2 reader; data stays in the browser tab and is not saved | Test build, 24 Nov 2026 | No reformatting for the team; nothing to leak |
| D19 | riskcore needs only numpy (normal quantile from Python's standard library, not scipy), and Pyodide is served from the site itself with pinned hashes | Test build, 24 Nov 2026 | Smaller, faster browser engine; no third-party scripts. Parity with v0.4.2 unchanged |
| D20 | The test website's front end is plain JavaScript with no build step; React+TypeScript is deferred until the page set settles | Test build, 24 Nov 2026 | Faster iteration on Hessa's feedback; revisit before team rollout |
| D21 | 'Stale' also covers holdings valued quarterly or yearly (instrument record, else observed pattern); the v0.4.2 zero-count rule is kept as stale_v042 for the parity test | Fix for V-02, 24 Nov 2026 | Quarterly funds had 67% zero months, under the 70% rule |
| D22 | Risk uses corrected returns for illiquid holdings by default: Geltner desmoothing for smoothed monthly funds (phi above 0.1 and 2/sqrt(n), capped at 0.7, cash excluded); quarterly funds modelled from equities this and last quarter (Dimson) plus their own residual variance; yearly funds only with an analyst-assumed beta. Switchable off; parity tests run with it off | Fix for V-01/V-03, awaiting validator re-review and Hessa's approval | Reported returns understated portfolio volatility (7.9% vs 9.1% true on the synthetic set) |
| D23 | Stress factors are matched to scenario roles by explicit mapping, then ticker or name; a scenario needing an unmatched factor is not run | Fix for V-04 | A renamed factor gave silent 0% shocks |
| D24 | Brinson: a weighted class with no index uses its own return, and the result lists those classes | Fix for V-05 | Previously crashed |
| D25 | Quarterly-valued funds: fund-specific variance is scaled up for appraisal smoothing, with monthly smoothing inferred from the residuals' quarterly autocorrelation and floored at 0.5 (an assumption, shown in the app) | Partial fix for V-18, 24 Nov 2026. Validator accepted as a Low limitation; approved by Hessa 24 Nov 2026 | 40 quarters cannot estimate within-quarter smoothing; typical published range 0.4 to 0.7 |
| D26 | A scenario role matched by name pattern to two or more factors is left unmatched (unless one name is exactly the role, or the analyst maps it) | Fix for V-17 | Two equity series must not both take the equity shock |
| D27 | The Liquidity page reads the monthly liquidity report and places each holding in a bucket from its own terms (timeline, then maximum days to cash: 1–5, 6–15, 16–40, 41–60 liquid; over 60 illiquid), not from hand-picked cell lists. Totals are reconciled to the report's own dashboard | 24 Nov 2026 | Rule-based placement cannot drop a row; a hand-built range can |
| D28 | "Max days" is taken as the worst case to cash and nothing is added. "+" means no redemption right. Blank terms go to "Terms missing" and count as not available. Gates, lock-ups and fees apply only when an analyst enters them; a comment that mentions one without an entry is flagged | Model Validator's requirements, 24 Nov 2026 | Free-text terms must not be guessed or read as "no gate". Hessa to confirm what max days includes |
| D29 | Liquidity limit = share of AUM in cash within a chosen horizon, set on the page (default 75% within 60 days) until Hessa confirms which rule applies | 24 Nov 2026 | The report carries more than one rule |
