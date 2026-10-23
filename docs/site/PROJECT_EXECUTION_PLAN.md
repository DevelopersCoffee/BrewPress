# Project execution plan: developerscoffee.com content engine

> **Source:** 2026-04-06 CEO plan "Technical Content Engine for Developers", a **historical snapshot**, not current state. Reconciled on 2026-10-23 IST against `DevelopersCoffee/BrewPress` `main` @ `bd843ff`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for evidence. Status words: Done, Pending, Blocked, Deferred, Needs verification.

This is a proposed order only. Every step is a separate PR on BrewPress, reviewed by Architect and merged by PR Governor. Nothing here publishes to WordPress, X, or Hacker News.

| Phase | Steps (backlog IDs) | Exit criteria | Status |
|---|---|---|---|
| 0. Baseline | Re-run the full suite on main | 657 passed, 0 failed on `bd843ff` (2026-10-23 IST) | Done |
| 0b. CI green | CI-1 | Lint (ruff) passes and Test runs green on main | Pending |
| 1. Safety for code posts | STR-1, STR-2, TEST-2 | Structurer never drops a fenced block and never crashes the run on bad JSON. Tests cover both. | Pending |
| 2. Loop quality | PIPE-2, PIPE-3, PIPE-4, TEST-1 | Max revisions returns the best draft. A ≥2-point drop exits early. boost_eval runs before Critic. Tests cover all three. | Pending |
| 3. Grounding | GND-1, then GND-2 | Critic or a check sees diff/notes and flags unsupported claims. `--pr-url` fetches PR content. | Pending |
| 4. UX + docs | UX-1, UX-2, ARCH-1, DOC-1 | Progress and per-round scores print. A single critic path. README reframed. | Pending |
| 5. Live site | SITE-1, SITE-2 | WordPress connected. One BrewPress post lands as a **WP draft** (no `--live`) on www.developerscoffee.com, and the owner checks it. | Blocked |
| 6. Config confirmations | CFG-1, CFG-2 | Architect confirms model choice and auto-approve gate | Needs verification |
| 7. Headless publish | DEF-4 | Only after phases 1–5, and only if the owner asks | Deferred |

Dependencies: Phase 5 is blocked on the site owner connecting WordPress. Phases 1–4 have no external dependency and can proceed in parallel. DEF-4 needs 2, 3 and 5.
