# BrewPress Architecture Decision Log

Decisions settled in the design and planning phase. Recorded here so future
implementation stacks do not re-litigate them.

---

## 1. argparse over typer for the CLI

**Decision:** Use `argparse` (stdlib) for the MVP CLI. Migrate to `typer` in Approach C
if the interface grows to warrant it. Do not mix both.

**Why:** `cli.py` stubs were already written with `argparse` before the design review.
The interface is small (7 subcommands) and `argparse` is sufficient. `typer` is deferred
to Approach C — it would add a dependency and require rewriting the existing stubs.
No functional benefit until the interface expands.

---

## 2. last_draft.json over SQLite for state persistence

**Decision:** Single JSON file at `~/.brewpress/last_draft.json`. No database.

**Why:**
- One active job at a time (by design). No relational queries needed.
- Reversible: delete the file, state is gone. No migrations, no schema versions to manage
  at the DB layer.
- Human-readable: user can inspect or manually edit state if needed.
- The tool is solo-use. SQLite's concurrency and integrity features are not needed.

State schema is versioned via `BlogJob.schema_version` to handle future field additions
without breaking existing state files.

---

## 3. Approach A → C → B delivery sequence

**Decision:** Ship in this order: single-agent MVP (A) → narrative scaffolding (C) →
full ADK multi-agent (B).

| Phase | What | Why |
|-------|------|-----|
| Approach A | Single Gemini Flash call, argparse CLI, httpx for WP | Proves diff → post pipeline works without hallucination. Ships this week. |
| Approach C | Two-step generation: diff → editable outline → prose | Fixes narrative quality, the real bottleneck (Codex challenge accepted). |
| Approach B | ADK multi-agent orchestration | Right long-term architecture, but a liability before generation quality is proven. |

**Stack mapping:** Stacks 1–6 are Approach A. Stack 4 refactor is Approach C.
Stack 8 is Approach B.

---

## 4. Per-subcommand config loading

**Decision:** `load_config(required=tuple)` — caller specifies which env vars it needs.
Fields for non-required vars are `None` on the returned `BrewPressConfig`.

**Why:** `calibrate` only needs WP credentials (reads posts, writes `tone.json`).
It should not fail when `GOOGLE_API_KEY` is absent. `draft` needs `GOOGLE_API_KEY`
but not necessarily WP credentials if the user hasn't set them up yet. A global
`load_config()` that hard-fails on all 4 vars blocks graceful degradation for any
subcommand that only needs a subset.

**Interface:**
```python
# draft subcommand (generation only)
cfg = load_config(required=("GOOGLE_API_KEY",))

# calibrate / approve-publish (WP only)
cfg = load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))

# full (both)
cfg = load_config()
```

---

## 5. Pydantic for BlogJob

**Decision:** `BlogJob` uses `pydantic.BaseModel` with `frozen=True`. Not a stdlib
`@dataclass`.

**Why:**

1. **Enum round-trip.** `json.dumps(dataclasses.asdict(job))` serializes `JobState.DRAFT`
   as `"DRAFT"` (string). Deserializing back requires manual enum reconstruction every
   time. Pydantic handles this automatically via `model_dump(mode="json")` and
   `model_validate()`.

2. **Consistency with Stack 4.** Stack 4 uses Pydantic's `response_schema` to parse
   Gemini Flash JSON output into a structured model. Using Pydantic for `BlogJob` in
   Stack 1 means one serialization pattern across the whole codebase — no refactor
   when Stack 4 arrives.

3. **Validation.** Pydantic validates field types on construction. A `state` field that
   receives a bad string raises a clear `ValidationError` immediately, not a silent
   wrong-state bug later.

---

## 6. Explicit transition methods over field validators

**Decision:** `BlogJob` exposes named transition methods (`mark_reviewed`,
`approve_content`, `approve_publish`, `reject`). The `state` field is never set
directly. Each method checks the current state and raises `ValueError` on an invalid
transition.

**Why field validators lose:**

- Pydantic `@model_validator` runs on every `model_copy()` call, including internal
  calls inside `StateStore.load()`. The validator would need to know whether a
  state assignment is a "transition" or a "load from disk" — that distinction is
  invisible to a field validator.
- `model_construct()` bypasses validators entirely. Any code path that uses it
  (e.g., performance-optimized deserialization) silently skips the guard.

**Why explicit methods win:**

- Each method is a named, testable contract: `approve_content()` documents its
  precondition in the method body and in the error message.
- `StateStore.load()` uses `model_validate()` which doesn't invoke transition logic —
  loading an `APPROVED_STEP_1` job from disk doesn't trigger the `REVIEWED →
  APPROVED_STEP_1` guard.
- Explicit > clever. The transition table is readable in the source.

---

## 7. Diff-grounded generation as primary, topic-only as supported

**Decision:** `--diff` and `--topic` are both optional on `brewpress draft`. At least
one must be provided. Diff-grounded generation is the primary use case and the product's
core differentiation.

**Why:** The PRD explicitly includes "Idea Post" (topic only, no code proof). Making
`--diff` optional preserves that path. Topic-only posts without a diff get no code
grounding — the LLM generates from topic alone, which is lower quality and more
hallucination-prone, but valid for conceptual posts.

**Rule:** When `--diff` is absent, `draft_body_md` quality is expected to be lower.
The quality score criteria still apply. The `is_single_topic` check still runs.
