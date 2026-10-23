# Project release checklist: developerscoffee.com content engine

> **Source:** 2026-04-06 CEO plan "Technical Content Engine for Developers", a **historical snapshot**, not current state. Reconciled on 2026-10-23 IST against `DevelopersCoffee/BrewPress` `main` @ `bd843ff`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for evidence. Status words: Done, Pending, Blocked, Deferred, Needs verification.

Gate for calling the content engine "release-ready for developerscoffee.com". No publish happens from this checklist. Live publish stays a separate, explicit owner decision.

| # | Check | Status | Evidence / note |
|---|---|---|---|
| 1 | Unit suite green on the release SHA | Done | 657 passed, 0 failed on `bd843ff`, run 2026-10-23 IST on Python 3.13.5. Re-run on the actual release SHA. |
| 2 | GitHub Actions CI green on the release SHA | Pending | On `bd843ff`, check runs show **Lint (ruff): failure** and **Test: skipped** (it depends on lint). Workflow: `.github/workflows/ci.yml` (`ruff check src/`). Locally, `ruff check src/` with the latest ruff on 2026-10-23 IST gives: Found 51 errors. |
| 3 | 4-agent loop wired in Orchestrator with max 3 rounds | Done | [orchestrator.py#L55](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L55), [#L164-L196](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L164-L196) |
| 4 | Structurer preserves code blocks (STR-1) | Pending | Not implemented |
| 5 | Best draft returned at max revisions (PIPE-2) | Pending | Not implemented; job is rejected |
| 6 | Grounding: claims checked against source (GND-1) | Pending | Not implemented |
| 7 | Two-step approval; WP **draft** by default; `--live` explicit only | Done | [wp_client.py#L440](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/wp_client.py#L440), [orchestrator.py#L299-L303](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L299-L303), [cli.py#L206-L208](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/cli.py#L206-L208) |
| 8 | Pipeline scaffolding stripped before publish | Done | [#5](https://github.com/DevelopersCoffee/BrewPress/pull/5), [#6](https://github.com/DevelopersCoffee/BrewPress/pull/6); `tests/test_publish_sanitizer.py` passes |
| 9 | Failure bundle written on publish error | Done | [orchestrator.py#L366-L370](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L366-L370) |
| 10 | www.developerscoffee.com connected (WordPress 7.1.3) | Blocked | Waiting on the site owner's WordPress connection |
| 11 | Live smoke: one post created as a WP draft, owner checked it in wp-admin | Blocked | Depends on #10 |
| 12 | Theme render check on live site (headings, code blocks, hero image) | Needs verification | Depends on #11 |
| 13 | README reframed to "Technical Content Engine for Developers" | Pending | DOC-1 |
| 14 | Headless / `--auto-publish` | Deferred | Out of release scope |
