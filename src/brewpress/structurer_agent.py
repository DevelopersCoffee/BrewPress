"""StructurerAgent — post structure enforcer.

Responsibility: H1/H2/H3 hierarchy, P→S→E section order, heading keywords.

Runs content.structure_summary first.  If the post already passes, returns
the job unchanged (no LLM call).  If issues are found, calls think() to
rewrite the body structure while preserving all factual content.

Pipeline position:
    WriterAgent  →  StructurerAgent.structure()  →  BlogJob (body restructured)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from brewpress.agent_base import BaseAgent
from brewpress.models import BlogJob


class _StructurerSchema(BaseModel):
    """Structured output schema — forces proper JSON escaping of markdown body."""

    draft_body_md: str

_MAX_BODY_CHARS = 6_000

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


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


def _build_prompt(job: BlogJob, issues: list[str]) -> str:
    body_preview = job.draft_body_md[:_MAX_BODY_CHARS]
    if len(job.draft_body_md) > _MAX_BODY_CHARS:
        body_preview += f"\n... [truncated at {_MAX_BODY_CHARS} chars]"

    issues_text = "\n".join(f"- {i}" for i in issues)
    return (
        f"Fix the structure of this blog post draft.\n\n"
        f"**Structural issues to fix:**\n{issues_text}\n\n"
        f"**Title:** {job.title}\n\n"
        f"**Body:**\n---\n{body_preview}\n---\n\n"
        "Return a JSON object with the restructured body only."
    )


class StructurerAgent(BaseAgent):
    """Structural editor that enforces heading hierarchy and P→S→E flow.

    Fast path: if content.structure_summary reports no issues, the job is
    returned unchanged without any LLM call.
    """

    SKILL: str | Path = "skills/structurer.md"
    TOOLS: list[str] = ["content.structure_summary"]

    def structure(self, job: BlogJob) -> BlogJob:
        """Enforce structural rules on the post body.

        Args:
            job: BlogJob in DRAFT state (after WriterAgent).

        Returns:
            BlogJob with draft_body_md rewritten if structure issues found.
            Returns the same job object if no issues detected (fast path).

        Raises:
            ValueError: Model returned invalid JSON.
        """
        result: dict[str, Any] = self.use(
            "content.structure_summary",
            body=job.draft_body_md,
            title=job.title,
            meta=job.meta_description,
        )

        issues: list[str] = result.get("issues") or []
        if not issues:
            return job  # fast path: structure already good

        prompt = _build_prompt(job, issues)
        raw = self.think(prompt, max_output_tokens=8192, response_schema=_StructurerSchema)
        return self._apply(job, raw)

    def _apply(self, job: BlogJob, raw: str) -> BlogJob:
        try:
            data: dict[str, Any] = json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"StructurerAgent returned invalid JSON: {exc}\n\nRaw (first 500 chars):\n{raw[:500]}"
            ) from exc

        new_body = str(data.get("draft_body_md") or "").strip()
        if not new_body:
            return job  # model returned empty body — keep original
        return job.model_copy(update={"draft_body_md": new_body})
