# Plan: Publish Pipeline — Clean Body + Smart Screenshot Selection

**Date:** 2026-05-04
**Trigger:** Post 796 (`git-worktree-ai-agents`) shipped to WP with three defects:
1. JSON command manifest + execution-proof block left in body (pipeline scaffolding leaked into reader content).
2. Terminal-command screenshots used instead of output screenshots → duplicate of the code block above.
3. Screenshots emitted for steps with empty output (`rm -rf`, `git init -q`).

**Goal:** BrewPress agent produces publish-ready posts without manual fixup. No regressions to existing draft generation.

---

## Spec

### S1. Body sanitizer — strip pipeline scaffolding before publish
Three section types are pipeline metadata, never reader content:
- `## Executed Tutorial Steps` … fenced JSON block … (next `##` heading)
- `## Execution Proof` … (next `##` heading)
- `## Screenshot Plan for the Blog Pipeline` … (next `##` heading or EOF)

**Where:** new pure function `sanitize_body_for_publish(body_md: str) -> str` in `src/brewpress/publish_sanitizer.py`. Called by `Orchestrator.publish()` immediately before `WordPressClient.publish()`.

**Behavior:** idempotent (no-op on already-clean body), preserves all other sections, regex-anchored on H2 headings only.

### S2. Smart screenshot selection — output over terminal, skip when empty
Current `sandbox_tutorial_media.generate_sandbox_tutorial_media()` emits both `TERMINAL_SCREENSHOT` and `OUTPUT_PROOF` for every step with `screenshot=True`.

**New rule:**
- For tutorial steps, emit `OUTPUT_PROOF` only when `result.stdout.strip()` OR `result.stderr.strip()` is non-empty (failure cases need stderr proof).
- Drop `TERMINAL_SCREENSHOT` from tutorial flow entirely (writer renders the command as a code block already; terminal-image is redundant).
- For non-tutorial code-post path (`media_agent.generate_for_code_post`), keep current behavior unchanged (PRD §Screenshot Rule still requires terminal+output).

**Why distinct paths:** `generate_for_code_post` is for general code posts (one-off command). `generate_sandbox_tutorial_media` is for multi-step tutorials where commands are already shown in body. Different contracts.

### S3. Hero image picker prefers output
`Orchestrator.publish()` line 333: `media_dir.glob("terminal_*.png")`.

**Change:** prefer `output_*.png`; fall back to `terminal_*.png` only if no output images exist.

### S4. Featured image set on every publish (currently inline-only)
Already works via `WordPressClient.publish(featured_media_id=...)` — verify call site in orchestrator passes the chosen hero ID. No new behavior, just confirm.

---

## Scope of THIS commit (`fix/publish-pipeline-clean-output`)

| File | Change |
|------|--------|
| `src/brewpress/publish_sanitizer.py` | NEW — `sanitize_body_for_publish()` |
| `tests/test_publish_sanitizer.py` | NEW — sanitizer unit tests (H2 strip, H1 boundary, idempotency, EOF, case-insensitive) |
| `docs/superpowers/plans/2026-05-04-publish-pipeline-clean-output.md` | NEW — this plan |

## Deferred (lands with sandbox + engagement tracks, not this commit)

| File | Change | Why deferred |
|------|--------|---|
| `src/brewpress/sandbox_tutorial_media.py` | Skip empty-output steps; emit output only | File is fully untracked; entangled with sandbox track WIP |
| `src/brewpress/orchestrator.py` | Glob `output_*.png` first; call sanitizer before publish | Tracked file already has pre-existing engagement-track diff; commit would conflate scopes |
| `tests/test_sandbox_tutorial_media_eval.py` | Empty-stdout + terminal-skip cases | Same as above |
| `tests/test_sandbox_git_media_eval.py` | New contract assertions | Same as above |
| `tests/test_orchestrator.py` | Hero-prefers-output test | Same as above |

These deferred changes have already been written and tested locally on this
worktree (691 passing). They're held back to keep this PR's blast radius
narrow. Follow-up PR after sandbox/engagement tracks merge.

No changes to writer_agent, models, wp_client, or media_agent core rendering.

---

## Test Strategy

### test_publish_sanitizer.py (new)
- `test_strips_executed_tutorial_steps_section` — input with section + JSON fenced block → section gone, sibling sections preserved.
- `test_strips_execution_proof_section` — same.
- `test_strips_screenshot_plan_section` — section at EOF (no following H2).
- `test_clean_body_unchanged` — body without any scaffolding → identical output.
- `test_idempotent` — sanitize(sanitize(x)) == sanitize(x).
- `test_does_not_strip_h3_or_inline_step_id_text` — only H2-anchored sections.

### test_sandbox_tutorial_media_eval.py (extend)
- `test_skips_step_with_empty_stdout` — runner returns `{"stdout": "", "exit_code": 0}` → no media item emitted for that step.
- `test_emits_only_output_not_terminal` — non-empty stdout → exactly one `OUTPUT_PROOF`, zero `TERMINAL_SCREENSHOT`.

### test_orchestrator.py (DEFERRED — lands with engagement track)
- `test_hero_prefers_output_image` — media dir with both `terminal_X.png` and `output_X.png` → orchestrator uploads `output_X.png` as hero.
- `test_hero_falls_back_to_terminal_when_no_output` — only terminal images present → uses terminal.
- `test_publish_calls_sanitizer_on_body` — assert `client.publish()` receives sanitized body.

---

## Implementation Steps

1. Write `publish_sanitizer.py` + tests. TDD: tests fail → implement → tests pass.
2. Modify `sandbox_tutorial_media.py`: add empty-stdout skip, drop terminal emission. Update existing tests for new contract.
3. Modify `orchestrator.py`: glob output first, call sanitizer in publish path.
4. Run full test suite (`pytest`) — confirm no regressions.
5. Re-run `scripts/republish_git_worktree_post.py` against post 796 — confirm body now clean WITHOUT manual sanitization in the script.
6. Commit.

---

## Acceptance Criteria

- `pytest tests/` passes.
- New `sanitize_body_for_publish()` strips all 3 scaffolding section types and is idempotent.
- Tutorial sandbox runner skips empty-output steps.
- Orchestrator picks `output_*.png` as hero when available.
- Re-running publish on post 796 (after reverting script's manual scaffolding strip) produces clean body identical to current state.

---

## Out of Scope

- Writer prompt changes to stop emitting scaffolding in the first place. (Drafts are mostly hand-authored; sanitizer is sufficient.)
- Media agent rendering changes (font, layout, palette).
- WP-side image styling.
- Header image generation pipeline (separate plan: `2026-05-04-blog-aware-header-image.md`).
