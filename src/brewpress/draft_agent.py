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

Style grounding is embedded in the system prompt as a normalized summary
of the DevelopersCoffee writing style.  A future stack will replace this
with a live corpus fingerprint from the calibrate command.

ADK integration note: DraftAgent wraps cleanly as an ADK LlmAgent.
The generate() method is the tool call boundary.
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob
from brewpress.work_ingestion import WorkContext

# ------------------------------------------------------------------ #
# Model selection                                                      #
# ------------------------------------------------------------------ #

_DEFAULT_MODEL = "gemini-2.0-flash"

# ------------------------------------------------------------------ #
# Style grounding                                                      #
# ------------------------------------------------------------------ #

# Normalized DevelopersCoffee style guide embedded in the system prompt.
# Replace this constant once the calibrate command builds tone.json.
_STYLE_GUIDE = textwrap.dedent("""\
    You are a technical blog writer for DevelopersCoffee.com — a backend-focused
    developer blog covering Java, Spring, AI agents, system design, and developer
    productivity.

    Writing rules (non-negotiable):
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
""")

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


# ------------------------------------------------------------------ #
# Prompt construction                                                  #
# ------------------------------------------------------------------ #

_MAX_DIFF_CHARS = 8_000   # keep prompts inside Flash context budget
_MAX_NOTES_CHARS = 2_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {limit} chars]"


def build_prompt(ctx: WorkContext) -> str:
    """Construct the generation prompt from a WorkContext.

    Exposed as a module-level function so tests can assert on prompt
    content without constructing a live DraftAgent.
    """
    parts: list[str] = []

    post_type = "CODE POST" if ctx.is_code_post else "IDEA POST"
    parts.append(f"## Task\n\nGenerate a {post_type} for DevelopersCoffee.com.\n")

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

# Gemini JSON mode returns clean JSON, but sometimes wraps it in a
# markdown fence — strip that before parsing.
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    m = _JSON_FENCE_RE.search(raw)
    return m.group(1) if m else raw.strip()


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
        prompt = build_prompt(ctx)

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=_STYLE_GUIDE,
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
