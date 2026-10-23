# Project backlog: developerscoffee.com content engine

> **Source:** 2026-04-06 CEO plan "Technical Content Engine for Developers", a **historical snapshot**, not current state. Reconciled on 2026-10-23 IST against `DevelopersCoffee/BrewPress` `main` @ `bd843ff`. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for evidence. Status words: Done, Pending, Blocked, Deferred, Needs verification.

Open work only. Done items are in PROJECT_STATUS.md. Priority: P1 = needed before headless or auto-publish, P2 = quality, P3 = docs and cleanup.

| ID | Item | Priority | Status | Why / evidence |
|---|---|---|---|---|
| SITE-1 | Connect www.developerscoffee.com (WordPress 7.1.3) to BrewPress (WP URL + application password) | P1 | Blocked | Needs the site owner's sign-in. Until then no live publish check is possible. |
| CI-1 | Fix `ruff check src/` so CI Lint passes and Test runs on main | P1 | Pending | On `bd843ff`, Lint (ruff) fails and Test is skipped. Locally: Found 51 errors. |
| SITE-2 | End-to-end smoke: `brewpress draft` → approve-content → approve-publish (draft, no `--live`) on the live site | P1 | Blocked | Depends on SITE-1 |
| GND-1 | Grounding check: Critic (or a deterministic step) checks claims against diff/notes, not just the draft | P1 | Pending | Critic prompt has no source context ([critic_agent.py#L121-L142](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/critic_agent.py#L121-L142)) |
| GND-2 | Fetch GitHub PR content for `--pr-url` (today it is stored, not fetched) | P2 | Pending | [work_ingestion.py#L60](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/work_ingestion.py#L60) |
| PIPE-2 | Best-draft tracking: return best-scoring draft at max revisions instead of rejecting | P1 | Pending | Plan #2. The plan's "--auto-publish" trajectory relies on it. Today: reject at [orchestrator.py#L192-L196](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/orchestrator.py#L192-L196) |
| PIPE-3 | Regression detection: any dimension drops ≥2 → early exit with best draft | P2 | Pending | Plan #3 |
| PIPE-4 | Run `boost_eval.run_checks` inside the loop before Critic (fail fast) | P2 | Pending | Plan #7. Only called from CLI today ([cli.py#L549](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/cli.py#L549)) |
| STR-1 | Structurer code-block preservation: fenced count must not drop → keep raw draft + warning | P1 | Pending | Plan #4. Code-heavy posts are the core audience. |
| STR-2 | Structurer invalid JSON → fall back to raw draft + warning instead of raising | P2 | Pending | Plan error registry. Today it raises ([structurer_agent.py#L86-L92](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/structurer_agent.py#L86-L92)) |
| UX-1 | Live per-stage progress `[pipeline] writer → structurer → seo → critic (round N/3)` | P3 | Pending | Plan #8 |
| UX-2 | Per-round scores and weakest dimension, including rejected runs | P3 | Pending | CLI-3 remainder |
| ARCH-1 | Retire `cli._run_critic_on_job` or move it into Orchestrator | P3 | Pending | Plan #6 ([cli.py#L509](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/cli.py#L509)) |
| DOC-1 | README reframe: "Technical Content Engine for Developers" + 4-agent pipeline description | P3 | Pending | Plan #9 |
| TEST-1 | Loop tests for best-draft and regression (plan's `test_pipeline_loop.py`, or extend `test_orchestrator.py`) | P2 | Pending | With PIPE-2 and PIPE-3 |
| TEST-2 | Structurer tests for code-block drop and JSON fallback | P2 | Pending | With STR-1 and STR-2 |
| CFG-1 | Confirm the production model for each agent (`BREWPRESS_MODEL`, default `gemini-2.0-flash`) | P3 | Needs verification | [agent_base.py#L90](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/agent_base.py#L90) |
| CFG-2 | Confirm auto-approve on critic pass is the intended "quality_score ≥ threshold" gate | P3 | Needs verification | CLI-1 wording vs [critic_agent.py#L57-L59](https://github.com/DevelopersCoffee/BrewPress/blob/bd843ffb44d622e563e2b4bf4255fb7c9cec1ad1/src/brewpress/critic_agent.py#L57-L59) |
| DEF-1 | `_llm_utils.py` / `_extract_json` dedup | — | Deferred | Superseded by `response_schema`. One copy is left in `blog_boost.py#L291`, and it could go the same way. |
| DEF-2 | Structurer `{content,title,meta_description}` schema | — | Deferred | Superseded by the `{draft_body_md}` schema |
| DEF-3 | BlogBoostAgent in loop + 429 skip warning | — | Deferred | Superseded by SEOAgent + tenacity retry |
| DEF-4 | `--auto-publish` (headless publish) | — | Deferred | The plan calls this long-term. It needs PIPE-2, GND-1, and SITE-2 first. |
