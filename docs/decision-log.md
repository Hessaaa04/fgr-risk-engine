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
