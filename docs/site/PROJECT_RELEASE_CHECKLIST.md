# Project release checklist: developerscoffee.com content engine

> **Source:** 2026-04-06 CEO plan "Technical Content Engine for Developers", a **historical snapshot**, not current state. Reconciled on 2026-10-23 IST against `DevelopersCoffee/BrewPress` `main` @ `bd843ff`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for evidence. Status words: Done, Pending, Blocked, Deferred, Needs verification.

Gate for calling the content engine "release-ready for developerscoffee.com". This checklist never publishes anything. Going live is a separate, explicit decision by the owner.

| # | Check | Status | Evidence / note |
|---|---|---|---|
| 1 | Unit suite green on the release SHA | Done | 657 passed, 0 failed on `bd843ff`, 2026-10-23 IST, Python 3.13.5. Re-run on the actual release SHA. |
| 2 | GitHub Actions CI green on the release SHA | Pending | On `bd843ff`: **Lint (ruff) failure**, **Test skipped**. `.github/workflows/ci.yml` runs `ruff check src/`. Locally: 51 errors (ruff 0.17.2). |
| 3 | Default and hard-coded model ids are current (not retired) | Pending | `gemini-2.0-flash` at [agent_base.py#L90](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/agent_base.py#L90), [blog_boost.py#L333](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/blog_boost.py#L333), [models/engagement_models.py#L30](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/models/engagement_models.py#L30). Google lists its shutdown as June 1, 2026 ([Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations)). RISK-1. |
| 4 | 4-agent loop wired in Orchestrator with max 3 rounds | Done | [orchestrator.py#L55](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L55), [orchestrator.py#L166-L196](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L166-L196). Live runs depend on `BREWPRESS_MODEL` being set, because the default `gemini-2.0-flash` is retired (RISK-1). |
| 5 | Structurer preserves code blocks (STR-1) | Pending | Not implemented |
| 6 | Best draft returned at max revisions (PIPE-2) | Pending | Not implemented; the job is rejected |
| 7 | Quality gate fails closed on missing score (QG-1) | Pending | Skips itself on `None` today ([review_gate.py#L176-L179](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/review_gate.py#L176-L179)) |
| 8 | Grounding: claims checked against source (GND-1) | Pending | Not implemented |
| 9 | Two-step approval; WP **draft** by default; `--live` explicit only | Done | [wp_client.py#L440](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/wp_client.py#L440), [orchestrator.py#L299-L303](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L299-L303), [cli.py#L206-L208](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/cli.py#L206-L208) |
| 10 | Pipeline scaffolding stripped before publish | Done | [#5](https://github.com/DevelopersCoffee/BrewPress/pull/5), [#6](https://github.com/DevelopersCoffee/BrewPress/pull/6); [orchestrator.py#L345-L350](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L345-L350); `tests/test_publish_sanitizer.py` passes |
| 11 | Failure bundle written on publish error | Done | [orchestrator.py#L366-L370](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L366-L370) |
| 12 | www.developerscoffee.com connected (WordPress 7.1.3) | Blocked | Waiting on the site owner's WordPress connection |
| 13 | Live smoke: one post created as a WP draft, owner checks it in wp-admin | Blocked | Depends on #12 and #3 |
| 14 | Theme render check on live site (headings, code blocks, hero image) | Blocked | Depends on #13 |
| 15 | README reframed to "Technical Content Engine for Developers" | Pending | DOC-1 |
| 16 | Headless / `--auto-publish` | Deferred | Out of release scope (the plan's long-term step) |
