"""SEOAgent — keyword placement and meta optimization.

Responsibility: title optimization, meta description, keyword density,
heading keyword placement.

Fast path (first pass only): if seo.full score >= 85 AND this is the first
pipeline attempt, skip the LLM call and return the job unchanged.  On revision
passes (job.revision_attempt > 0), always call think() to validate that
WriterAgent's rewrite didn't introduce SEO regressions.

Pipeline position:
    StructurerAgent  →  SEOAgent.optimize()  →  BlogJob (SEO-optimized)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from brewpress.agent_base import BaseAgent
from brewpress.models import BlogJob

_MAX_BODY_CHARS = 6_000
_SEO_FAST_PATH_THRESHOLD = 85

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


class _SEOSchema(BaseModel):
    """Structured output schema — forces proper JSON escaping of markdown content."""

    title: str
    meta_description: str
    draft_body_md: str


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


def _build_prompt(job: BlogJob, seo_result: dict[str, Any]) -> str:
    body_preview = job.draft_body_md[:_MAX_BODY_CHARS]
    if len(job.draft_body_md) > _MAX_BODY_CHARS:
        body_preview += f"\n... [truncated at {_MAX_BODY_CHARS} chars]"

    checks = seo_result.get("checks") or {}
    issues_parts: list[str] = []

    title_check = checks.get("title") or {}
    if not title_check.get("in_range"):
        issues_parts.append(
            f"- Title length {title_check.get('char_count', '?')} chars "
            f"(need 50–60). Current: '{job.title}'"
        )

    meta_check = checks.get("meta") or {}
    if not meta_check.get("in_range"):
        issues_parts.append(
            f"- Meta description {meta_check.get('char_count', '?')} chars "
            f"(need 120–160). Current: '{job.meta_description}'"
        )

    kw_check = checks.get("keywords") or {}
    missing_kw = kw_check.get("missing") or []
    if missing_kw:
        issues_parts.append(f"- Missing keywords: {', '.join(missing_kw)}")

    heading_check = checks.get("headings") or {}
    heading_issues = heading_check.get("issues") or []
    for h in heading_issues:
        issues_parts.append(f"- Heading: {h}")

    issues_text = "\n".join(issues_parts) or "- General SEO improvements needed"

    return (
        f"Improve SEO for this blog post. Current score: {seo_result.get('score', 0)}/100.\n\n"
        f"**Issues to fix:**\n{issues_text}\n\n"
        f"**Title:** {job.title}\n"
        f"**Meta description:** {job.meta_description}\n"
        f"**Primary keyword:** {job.primary_keyword}\n"
        f"**Secondary keywords:** {', '.join(job.secondary_keywords)}\n\n"
        f"**Body:**\n---\n{body_preview}\n---\n\n"
        "Return a JSON object with improved title, meta_description, and draft_body_md."
    )


class SEOAgent(BaseAgent):
    """SEO optimizer for title, meta description, and keyword placement.

    Fast path: skips LLM if seo.full score >= 85 on the first pipeline pass
    (job.revision_attempt == 0).  Always calls think() on revision passes to
    catch cumulative SEO regressions introduced by WriterAgent rewrites.
    """

    SKILL: str | Path = "skills/seo.md"
    TOOLS: list[str] = ["seo.full"]

    def optimize(self, job: BlogJob) -> BlogJob:
        """Apply SEO improvements to the post.

        Args:
            job: BlogJob in DRAFT state (after StructurerAgent).

        Returns:
            BlogJob with title, meta_description, and draft_body_md updated.
            Returns the same job object on the fast path (first pass, score >= 85).

        Raises:
            ValueError: Model returned invalid JSON.
        """
        result: dict[str, Any] = self.use(
            "seo.full",
            title=job.title,
            meta=job.meta_description,
            body=job.draft_body_md,
            primary_keyword=job.primary_keyword,
            secondary_keywords=job.secondary_keywords,
        )

        score: int = result.get("score", 0)

        # Fast path: only skip LLM on the very first attempt and only when score is good.
        # On revision passes (revision_attempt > 0), always validate — WriterAgent rewrites
        # can silently drop keyword placement even when the structural issues are fixed.
        if score >= _SEO_FAST_PATH_THRESHOLD and job.revision_attempt == 0:
            return job

        prompt = _build_prompt(job, result)
        raw = self.think(prompt, max_output_tokens=8192, response_schema=_SEOSchema)
        return self._apply(job, raw)

    def _apply(self, job: BlogJob, raw: str) -> BlogJob:
        try:
            data: dict[str, Any] = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"SEOAgent returned invalid JSON: {exc}\n\nRaw (first 500 chars):\n{raw[:500]}"
            ) from exc

        updates: dict[str, Any] = {}
        if new_title := str(data.get("title") or "").strip():
            updates["title"] = new_title
        if new_meta := str(data.get("meta_description") or "").strip():
            updates["meta_description"] = new_meta
        if new_body := str(data.get("draft_body_md") or "").strip():
            updates["draft_body_md"] = new_body

        if not updates:
            return job
        return job.model_copy(update=updates)
