"""WriterAgent — narrative-first blog post generator.

Responsibility: narrative arc only.
    Hook/problem → conflict/struggle → resolution/solution

This agent does NOT apply SEO hints or structure hints — those are handled
by StructurerAgent and SEOAgent downstream.  Keeping concerns separate means
each revision pass only touches what it owns.

Pipeline position:
    WorkContext  →  WriterAgent.generate()  →  BlogJob (DRAFT)
    BlogJob (with revise_instruction)  →  WriterAgent.generate()  →  BlogJob (DRAFT)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from brewpress.agent_base import BaseAgent
from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob
from brewpress.work_ingestion import WorkContext

_MAX_BODY_CHARS = 6_000
_MAX_DIFF_CHARS = 4_000

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


class _WriterSchema(BaseModel):
    """Structured output schema for WriterAgent — forces proper JSON escaping."""

    title: str
    slug: str
    meta_description: str
    excerpt: str
    primary_keyword: str
    secondary_keywords: list[str]
    outline: list[str]
    draft_body_md: str
    hook: str
    cta: str


def _extract_json(raw: str) -> str:
    text = raw.strip().lstrip("\ufeff").strip()
    if text.startswith("{"):
        return text
    text = _JSON_FENCE_RE.sub("", text, count=1).strip()
    if text.startswith("{"):
        return text.rstrip("`").rstrip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _build_prompt(ctx: WorkContext, revise_instruction: str) -> str:
    parts: list[str] = []

    if revise_instruction:
        parts.append(f"[REVISION REQUIRED]\n{revise_instruction}\n")

    parts.append(f"Topic: {ctx.topic or '(derived from diff)'}")

    if ctx.notes:
        parts.append(f"Notes:\n{ctx.notes}")

    if ctx.diff and ctx.diff.raw:
        diff_preview = ctx.diff.raw[:_MAX_DIFF_CHARS]
        if len(ctx.diff.raw) > _MAX_DIFF_CHARS:
            diff_preview += f"\n... [diff truncated at {_MAX_DIFF_CHARS} chars]"
        parts.append(f"Diff:\n```diff\n{diff_preview}\n```")

    if ctx.pr_url:
        parts.append(f"PR URL: {ctx.pr_url}")

    return "\n\n".join(parts)


class WriterAgent(BaseAgent):
    """Narrative-arc blog post generator.

    Reads skills/draft.md as its system prompt.  Produces a full BlogJob
    with title, meta description, keywords, outline, hook, cta, and body.

    On revision passes, the revise_instruction from CriticAgent is prepended
    to the prompt so the model knows what specifically to fix.
    """

    SKILL: str | Path = "skills/draft.md"
    TOOLS: list[str] = []  # WriterAgent is pure LLM — no tools needed

    def generate(self, ctx: WorkContext, force: bool = False) -> BlogJob:
        """Generate a blog post draft from a WorkContext.

        Args:
            ctx:   WorkContext from work_ingestion.ingest().
            force: Skip multi-topic guard (passed through from CLI --force).

        Returns:
            BlogJob in DRAFT state with all content fields populated.

        Raises:
            ValueError: Multi-topic post detected and force=False.
            ValueError: Model returned invalid JSON.
        """
        # Carry forward revision context from a previous loop pass
        revise_instruction = ctx.revise_instruction if hasattr(ctx, "revise_instruction") else ""
        prompt = _build_prompt(ctx, revise_instruction)
        raw = self.think(prompt, max_output_tokens=8192, response_schema=_WriterSchema)
        return self._parse(raw, force=force)

    def generate_revision(self, job: BlogJob, ctx: WorkContext) -> BlogJob:
        """Re-generate a draft using the revision instruction stored in job.

        Called by Orchestrator on loop iterations where critic verdict = "revise".
        """
        prompt = _build_prompt(ctx, job.revise_instruction)
        raw = self.think(prompt, max_output_tokens=8192, response_schema=_WriterSchema)
        return self._parse(raw, force=True)  # force=True: multi-topic guard already passed

    def _parse(self, raw: str, force: bool) -> BlogJob:
        try:
            data: dict[str, Any] = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"WriterAgent returned invalid JSON: {exc}\n\nRaw (first 500 chars):\n{raw[:500]}"
            ) from exc

        is_single = bool(data.get("is_single_topic", True))
        if not is_single and not force:
            raise ValueError(
                "WriterAgent flagged a multi-topic post. "
                "Use --force to override and generate anyway."
            )

        return BlogJob(
            title=str(data.get("title") or ""),
            slug=str(data.get("slug") or ""),
            meta_description=str(data.get("meta_description") or ""),
            excerpt=str(data.get("excerpt") or ""),
            primary_keyword=str(data.get("primary_keyword") or ""),
            secondary_keywords=list(data.get("secondary_keywords") or []),
            tags=list(data.get("tags") or []),
            categories=list(data.get("categories") or []),
            outline=list(data.get("outline") or []),
            draft_body_md=str(data.get("draft_body_md") or ""),
            hook=str(data.get("hook") or ""),
            cta=str(data.get("cta") or ""),
            is_single_topic=is_single,
            quality_score=int(data["quality_score"]) if data.get("quality_score") is not None else None,
            quality_gaps=list(data.get("quality_gaps") or []),
        )
