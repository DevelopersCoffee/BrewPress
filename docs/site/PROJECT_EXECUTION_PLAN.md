# Project execution plan: developerscoffee.com content engine

> **Source:** 2026-04-06 CEO plan "Technical Content Engine for Developers", a **historical snapshot**, not current state. Reconciled on 2026-10-23 IST against `DevelopersCoffee/BrewPress` `main` @ `bd843ff`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for evidence. Status words: Done, Pending, Blocked, Deferred, Needs verification.

Proposed order. Each step is a separate BrewPress PR: Architect reviews, PR Governor merges. Nothing here publishes to WordPress, X, or Hacker News.

| Phase | Steps (backlog IDs) | Exit criteria | Status |
|---|---|---|---|
| 0. Baseline | Re-run the full suite on main | 657 passed, 0 failed on `bd843ff` (2026-10-23 IST) | Done |
| 0a. Model migration | RISK-1 | No retired model id in the code (today: [agent_base.py#L90](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/agent_base.py#L90), [blog_boost.py#L333](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/blog_boost.py#L333), [models/engagement_models.py#L30](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/models/engagement_models.py#L30)). Per-agent override exists. | Pending |
| 0b. CI green | CI-1 | Lint (ruff) passes and Test runs green on main | Pending |
| 1. Safety for code posts | STR-1, STR-2, TEST-2 | Structurer never drops a fenced block and never crashes the run on bad JSON. Tests cover both. | Pending |
| 2. Loop quality | PIPE-2, PIPE-3, PIPE-4, QG-1, TEST-1 | Best draft returned at max revisions. Early exit on a ≥2 drop. boost_eval runs before Critic. Quality gate fails closed. Tests cover all of it. | Pending |
| 3. Grounding | GND-1, then GND-2 | Critic or a check sees diff/notes and flags unsupported claims. `--pr-url` is fetched. | Pending |
| 4. UX + docs | UX-1, UX-2, ARCH-1, DOC-1 | Progress and per-round scores print. A single critic path. README reframed. | Pending |
| 5. Live site | SITE-1, SITE-2 | WordPress connected. One post lands as a **WP draft** (no `--live`) on www.developerscoffee.com, and the owner checks it. | Blocked |
| 6. Headless publish | DEF-4 | Only after phases 0a–5, and only if the owner asks | Deferred |

Dependencies: phase 0a must land before any live run (SITE-2). Phase 5 is blocked on the site owner connecting WordPress. Phases 0b–4 have no external dependency. DEF-4 needs phases 0a–5.
