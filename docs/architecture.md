# Architecture (Stage 1)

A private website that delivers code only. Users open it in Chrome or Edge on work PCs,
load Excel files from their PC or the shared drive, and every calculation runs in their
browser. Portfolio data never reaches the website host, GitHub or any server.

```
GitHub (code, synthetic data) --> static website host (code only, sign-in protected)
                                            |
                                     app code only
                                            v
           Work PC browser: front end --> riskcore (Python via WebAssembly) --> local store
                    ^
                    | load Excel, save encrypted dataset files and reports
           Work PC folders and shared drive (real data stays here)
```

| Part | Choice | Status |
| --- | --- | --- |
| Calculation library | `riskcore/`, Python, pure functions | Phase 0: core risk, active risk, factors, PCA, stress, reverse stress, Brinson ported and parity-tested |
| Synthetic data | `synthetic/`, deterministic generator and workbook writer | Phase 0: done |
| Browser runtime for Python | Pyodide (WebAssembly) | Phase 1 |
| Front end | React + TypeScript | Phase 1 |
| Dataset files | Encrypted file with data versions, change log, sign-off, source-file fingerprints | Phase 1 |
| Hosting | Static host with sign-in protection (Cloudflare Pages or Vercel, decided in Phase 1) | Phase 1 |
| Stage 2 | Python API + PostgreSQL on organisation-owned hosting | Later |

Website safeguards: strict content security policy (no outbound data), no third-party
scripts, pinned dependencies, reviewed releases only, two-factor authentication on GitHub
and the hosting account.
