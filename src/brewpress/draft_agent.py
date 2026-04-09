"""Draft Agent — structured blog generation via Gemini Flash.

Consumes a WorkContext (Stack 3) and returns a populated BlogJob in
DRAFT state ready for review.

Pipeline position:
    WorkContext  →  DraftAgent.generate()  →  BlogJob (DRAFT)

Generation contract:
    - Title contains the primary keyword.
    - Primary keyword appears in the first H2 or the intro paragraph.
    - meta_description is 150–160 characters.
    - Exactly 3 secondary keywords.
    - Content grounded in the provided diff/notes; no invented facts.
    - Short paragraphs. No fluff. Practical developer tone.

Style grounding is embedded in the system prompt as a normalized writing guide.
When `brewpress calibrate` has run, the tone fingerprint from `~/.brewpress/tone.json`
is appended to the system prompt automatically.

ADK integration note: DraftAgent wraps cleanly as an ADK LlmAgent.
The generate() method is the tool call boundary.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob
from brewpress.work_ingestion import WorkContext

# ------------------------------------------------------------------ #
# Model selection                                                      #
# ------------------------------------------------------------------ #

_DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"

# ------------------------------------------------------------------ #
# Style grounding                                                      #
# ------------------------------------------------------------------ #

_WRITING_RULES = textwrap.dedent("""\
    ## Writing rules (non-negotiable)
    - Lead with value. First sentence tells the reader what they will learn or do.
    - Short paragraphs: 2–3 sentences max. One idea per paragraph.
    - Active voice. No "it can be seen that", "it is important to note".
    - No fluff: no "In today's fast-paced world", no excessive preamble.
    - Code blocks for all code, shell commands, and expected output.
    - H2 for major sections, H3 for sub-sections.
    - Practical examples beat abstract explanations.
    - Do not invent facts. Only state what the provided context supports.
    - Internal tone: confident, direct, slightly opinionated, technically exact.
    - Audience: mid-to-senior backend developers. No hand-holding, no basics recap.

    ## Post structure (Problem → Solution → Expansion)
    Follow this arc unless the content clearly dictates otherwise:

    1. Hook (intro): Start in the middle of the problem or at a moment of friction.
       State what the reader will build or learn. 2–3 tight sentences. No throat-clearing.
    2. Prerequisites / Setup: List what the reader needs before starting.
    3. Core walkthrough: Show the working code or configuration first, then explain it.
       "Here is what changed — here is why it works" beats theory-before-code.
    4. Running / debugging section: Show real terminal output. Describe the "Aha!" moment.
    5. Leveling up (optional): One advanced pattern or real-world extension.
    6. Summary + CTA: What did we learn? Give one clear next step or challenge.

    ## Storytelling
    - Audiences remember stories 22× more than lists of facts.
    - Show, don't just tell: "The terminal flickered with life" > "it worked".
    - Address the reader as "you" — they are the hero, not you.
    - Share real friction: errors, wrong turns, and fixes make posts credible.
    - Control pacing: short sentences for high-tension moments; longer for explanation.
""")


def _build_style_guide(
    site_name: str,
    site_focus: str,
    tone_fingerprint: dict | None = None,
) -> str:
    """Build the system-prompt style guide from site identity and optional tone data."""
    header = (
        f"You are a technical blog writer for {site_name} — a {site_focus} blog.\n\n"
    )
    guide = header + _WRITING_RULES

    if tone_fingerprint:
        # Inject the site's actual voice fingerprint when calibrate has run.
        tone_section = "\n## Site tone fingerprint (from calibrate)\n"
        for key, value in tone_fingerprint.items():
            tone_section += f"- {key}: {value}\n"
        guide += tone_section

    return guide

# ------------------------------------------------------------------ #
# Draft schema (structured output contract)                           #
# ------------------------------------------------------------------ #

# Maximum number of secondary keywords — matches PRD §SEO Agent.
_SECONDARY_KEYWORD_COUNT = 3


class DraftSchema(BaseModel):
    """Structured output expected from Gemini for each generation request.

    Used as the response_schema for JSON-mode generation, ensuring the
    model returns a parse-ready object rather than free-form text.
    """

    title: str = Field(description="Post title. Must contain the primary keyword.")
    slug: str = Field(
        description=(
            "URL slug: lowercase, hyphenated, no special characters. "
            "Derived from the title."
        )
    )
    meta_description: str = Field(
        description=(
            "SEO meta description. 150–160 characters. "
            "Contains the primary keyword naturally."
        )
    )
    excerpt: str = Field(
        description="2–3 sentence teaser shown in post listings. No spoilers."
    )
    primary_keyword: str = Field(
        description="Single primary SEO keyword. Appears in title and intro."
    )
    secondary_keywords: list[str] = Field(
        description=f"Exactly {_SECONDARY_KEYWORD_COUNT} supporting SEO keywords.",
        min_length=1,
        max_length=_SECONDARY_KEYWORD_COUNT,
    )
    outline: list[str] = Field(
        description="Ordered list of H2 section headings for the post."
    )
    draft_body_md: str = Field(
        description=(
            "Full post body in Markdown. Follows the outline. "
            "All code in fenced code blocks with language hint."
        )
    )
    is_single_topic: bool = Field(
        description=(
            "True when the post covers one cohesive topic. "
            "False when it attempts to cover multiple unrelated topics."
        )
    )
    tags: list[str] = Field(description="WordPress tags (3–6 entries).")
    categories: list[str] = Field(
        description="WordPress categories (1–2 entries, e.g. 'Backend', 'Java')."
    )
    quality_score: int = Field(
        description=(
            "Self-assessed quality score 0–100. "
            "100 = publish-ready with zero edits. "
            "Deduct for: missing code proof, weak intro, thin content, "
            "keyword stuffing, invented facts."
        ),
        ge=0,
        le=100,
    )
    quality_gaps: list[str] = Field(
        description=(
            "Specific gaps that lower quality_score. "
            "Empty when quality_score is 90+."
        )
    )
    hook: str = Field(
        description=(
            "2–3 sentence opening hook. Starts in the middle of the problem. "
            "Tells the reader exactly what they will learn or build. No fluff."
        )
    )
    cta: str = Field(
        description=(
            "1–2 sentence call-to-action at the end. "
            "Gives the reader a clear next challenge or resource."
        )
    )


# ------------------------------------------------------------------ #
# Prompt construction                                                  #
# ------------------------------------------------------------------ #

_MAX_DIFF_CHARS = 8_000   # keep prompts inside Flash context budget
_MAX_NOTES_CHARS = 2_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {limit} chars]"


def build_prompt(ctx: WorkContext, site_name: str = "my technical blog") -> str:
    """Construct the generation prompt from a WorkContext.

    Exposed as a module-level function so tests can assert on prompt
    content without constructing a live DraftAgent.
    """
    parts: list[str] = []

    post_type = "CODE POST" if ctx.is_code_post else "IDEA POST"
    parts.append(f"## Task\n\nGenerate a {post_type} for {site_name}.\n")

    parts.append(f"**Topic:** {ctx.topic}")

    if ctx.notes:
        parts.append(f"**Notes:**\n{_truncate(ctx.notes, _MAX_NOTES_CHARS)}")

    if ctx.commands:
        cmds_block = "\n".join(f"$ {c}" for c in ctx.commands)
        parts.append(f"**Runnable commands extracted from context:**\n```\n{cmds_block}\n```")

    if ctx.diff:
        parts.append(
            f"**Files changed:** {', '.join(ctx.diff.files_changed) or 'none'}"
        )
        parts.append(
            f"**Git diff (grounding — do not invent beyond this):**\n"
            f"```diff\n{_truncate(ctx.diff.raw, _MAX_DIFF_CHARS)}\n```"
        )

    if ctx.pr_url:
        parts.append(
            f"**PR URL (Phase 2 — do not fetch; use as attribution reference):** {ctx.pr_url}"
        )

    parts.append(
        "\n## Output requirements\n\n"
        "Return a single JSON object matching the provided schema.\n"
        "- Title must contain the primary keyword.\n"
        "- Primary keyword must appear in the first H2 or the intro paragraph.\n"
        f"- Exactly {_SECONDARY_KEYWORD_COUNT} secondary keywords.\n"
        "- meta_description must be 150–160 characters.\n"
        "- No invented facts — stay within what the context provides.\n"
        "- Every code example must be in a fenced code block with a language hint.\n"
    )

    return "\n\n".join(parts)


# ------------------------------------------------------------------ #
# Response parsing                                                     #
# ------------------------------------------------------------------ #

# Gemini may wrap its JSON response in a markdown fence.  The greedy outer
# fence regex is intentionally avoided here because the JSON body itself can
# contain fenced code blocks (e.g. ```java … ```), which would cause a
# non-greedy inner match to terminate early and return an empty / partial
# string.  Instead we locate the outermost { … } span after stripping any
# fence header.
_JSON_FENCE_HEADER_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


def _extract_json(raw: str) -> str:
    """Return the first complete JSON object found in *raw*.

    Handles three response shapes:
      1. Bare JSON object (most common with response_mime_type=application/json).
      2. JSON object wrapped in a ```json … ``` markdown fence.
      3. Any other text with an embedded JSON object.
    """
    # Strip BOM and surrounding whitespace.
    text = raw.strip().lstrip("\ufeff").strip()

    # Fast path: already a bare JSON object.
    if text.startswith("{"):
        return text

    # Strip a leading fence header (``` or ```json) so the remainder starts
    # at the opening brace, then fall through to the { … } extractor below.
    text = _JSON_FENCE_HEADER_RE.sub("", text, count=1).strip()
    if text.startswith("{"):
        # Strip a trailing ``` fence closer if present.
        if text.endswith("```"):
            text = text[: text.rfind("```")].rstrip()
        return text

    # Last resort: find the outermost { … } span in whatever was returned.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]

    return text


def parse_draft_response(raw: str) -> DraftSchema:
    """Parse the model's text response into a validated DraftSchema.

    Raises:
        ValueError: If the response cannot be parsed or fails schema validation.
    """
    try:
        data: dict[str, Any] = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}\n\nRaw response:\n{raw}") from exc

    # Clamp secondary_keywords to the expected count before validation so
    # that minor model over-generation doesn't hard-fail the whole call.
    if isinstance(data.get("secondary_keywords"), list):
        data["secondary_keywords"] = data["secondary_keywords"][:_SECONDARY_KEYWORD_COUNT]

    try:
        return DraftSchema.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Model response failed schema validation: {exc}") from exc


# ------------------------------------------------------------------ #
# BlogJob construction from DraftSchema                               #
# ------------------------------------------------------------------ #


def draft_to_job(draft: DraftSchema) -> BlogJob:
    """Convert a validated DraftSchema into a BlogJob in DRAFT state."""
    return BlogJob(
        title=draft.title,
        slug=draft.slug,
        meta_description=draft.meta_description,
        excerpt=draft.excerpt,
        primary_keyword=draft.primary_keyword,
        secondary_keywords=draft.secondary_keywords,
        tags=draft.tags,
        categories=draft.categories,
        outline=draft.outline,
        draft_body_md=draft.draft_body_md,
        is_single_topic=draft.is_single_topic,
        quality_score=draft.quality_score,
        quality_gaps=draft.quality_gaps,
        hook=draft.hook,
        cta=draft.cta,
    )


# ------------------------------------------------------------------ #
# DraftAgent                                                           #
# ------------------------------------------------------------------ #


class DraftAgent:
    """Generate a structured blog draft from a WorkContext.

    Args:
        config: BrewPressConfig with google_api_key set.
        model:  Gemini model name. Defaults to gemini-2.0-flash.

    Example:
        config = load_config(required=("GOOGLE_API_KEY",))
        agent = DraftAgent(config)
        job = agent.generate(ctx)
    """

    def __init__(
        self,
        config: BrewPressConfig,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        if not config.google_api_key:
            raise ValueError(
                "DraftAgent requires GOOGLE_API_KEY. "
                "Run 'brewpress draft' after setting the environment variable."
            )
        # Import deferred to avoid mandatory dependency at import time — callers
        # that never use DraftAgent (e.g. tests of other modules) stay unaffected.
        from google import genai
        from google.genai import types as _types

        self._client = genai.Client(api_key=config.google_api_key)
        self._model = model
        self._types = _types
        self._site_name = config.site_name
        self._site_focus = config.site_focus

        # Load tone fingerprint from calibrate if available; silent miss is fine.
        tone_path = Path.home() / ".brewpress" / "tone.json"
        self._tone_fingerprint: dict | None = None
        if tone_path.exists():
            try:
                self._tone_fingerprint = json.loads(tone_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass  # corrupt or unreadable tone.json — fall back to defaults

    def generate(self, ctx: WorkContext, force: bool = False) -> BlogJob:
        """Generate a draft BlogJob from a WorkContext.

        Args:
            ctx:   Normalized work context (topic, notes, diff, commands).
            force: When True, skip the is_single_topic guard and generate
                   regardless of scope check (maps to --force on the CLI).

        Returns:
            BlogJob in DRAFT state with all content fields populated.

        Raises:
            ValueError: If the model response cannot be parsed or validated.
            google.genai.errors.APIError: On API-level failures.
        """
        prompt = build_prompt(ctx, site_name=self._site_name)
        style_guide = _build_style_guide(
            self._site_name,
            self._site_focus,
            self._tone_fingerprint,
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=style_guide,
                response_mime_type="application/json",
                response_schema=DraftSchema,
                temperature=0.4,   # low temperature for factual grounding
                max_output_tokens=8192,
            ),
        )

        raw = response.text or ""
        draft = parse_draft_response(raw)

        if not force and not draft.is_single_topic:
            raise ValueError(
                "Generated draft covers multiple topics (is_single_topic=False). "
                "Narrow your topic or pass force=True to generate anyway."
            )

        return draft_to_job(draft)
