"""Critic Agent — LLM-based post review and revision gating.

Implements the Generator + Critic loop pattern from the ADK spec.

The critic evaluates a BlogJob draft on four dimensions and returns a
structured verdict.  When the verdict is "revise", the Orchestrator feeds
the revision_instruction back into the next WriterAgent pass.

Pipeline position:
    SEOAgent  →  CriticAgent.review()  →  CriticResult
                                │
                       verdict == "revise"
                                │
                 job.model_copy(revise_instruction=...)
                                │
                    WriterAgent (next loop iteration)

Scoring:
    Each dimension is scored 1–5 by the model.
    verdict = "pass"   when ALL scores >= PASS_THRESHOLD (default 4)
    verdict = "revise" when ANY score < PASS_THRESHOLD

The verdict rule is enforced deterministically in code — the model's
self-reported verdict is overridden if it disagrees with the scores.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from brewpress.agent_base import BaseAgent
from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob

# ------------------------------------------------------------------ #
# Pass threshold                                                       #
# ------------------------------------------------------------------ #

PASS_THRESHOLD: int = 4  # minimum score per dimension to pass

# ------------------------------------------------------------------ #
# Result model                                                         #
# ------------------------------------------------------------------ #


class CriticScores(BaseModel):
    seo_quality: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    technical_accuracy: int = Field(ge=1, le=5)
    publish_readiness: int = Field(ge=1, le=5)

    def all_pass(self, threshold: int = PASS_THRESHOLD) -> bool:
        return all(
            s >= threshold
            for s in [
                self.seo_quality,
                self.clarity,
                self.technical_accuracy,
                self.publish_readiness,
            ]
        )

    def lowest(self) -> tuple[str, int]:
        fields = {
            "seo_quality": self.seo_quality,
            "clarity": self.clarity,
            "technical_accuracy": self.technical_accuracy,
            "publish_readiness": self.publish_readiness,
        }
        key = min(fields, key=lambda k: fields[k])
        return key, fields[key]


class _CriticSchema(BaseModel):
    """Structured output schema for CriticAgent — forces proper JSON escaping."""

    scores: CriticScores
    verdict: Literal["pass", "revise"]
    revision_instruction: str
    failures: list[str]


@dataclass(frozen=True)
class CriticResult:
    """Structured output from a CriticAgent review pass."""

    verdict: Literal["pass", "revise"]
    revision_instruction: str
    scores: CriticScores
    failures: list[str]

    def is_pass(self) -> bool:
        return self.verdict == "pass"

    def summary(self) -> str:
        """Human-readable one-liner for CLI output."""
        dim, score = self.scores.lowest()
        if self.is_pass():
            return (
                f"[PASS] All dimensions scored {PASS_THRESHOLD}+. "
                f"Weakest: {dim} ({score}/5)."
            )
        return (
            f"[REVISE] {dim} scored {score}/5 — "
            f"{self.revision_instruction[:120]}"
        )


# ------------------------------------------------------------------ #
# Prompt builder                                                       #
# ------------------------------------------------------------------ #

_MAX_BODY_CHARS = 6_000

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.MULTILINE)


def _build_critic_prompt(job: BlogJob) -> str:
    body_preview = job.draft_body_md[:_MAX_BODY_CHARS]
    if len(job.draft_body_md) > _MAX_BODY_CHARS:
        body_preview += f"\n... [truncated at {_MAX_BODY_CHARS} chars]"

    kw_list = ", ".join(
        [job.primary_keyword or ""] + list(job.secondary_keywords or [])
    ).strip(", ")

    quality_note = ""
    if job.quality_score is not None:
        gaps = "; ".join(job.quality_gaps or []) or "none listed"
        quality_note = (
            f"\nDraftAgent self-score: {job.quality_score}/100 — gaps: {gaps}"
        )

    return (
        f"Review this blog post draft.\n\n"
        f"**Title:** {job.title}\n"
        f"**Meta description:** {job.meta_description}\n"
        f"**Primary keyword:** {job.primary_keyword}\n"
        f"**Keywords:** {kw_list}"
        f"{quality_note}\n\n"
        f"**Body:**\n---\n{body_preview}\n---"
    )


# ------------------------------------------------------------------ #
# Response parsing                                                     #
# ------------------------------------------------------------------ #


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


def _parse_critic_response(raw: str) -> CriticResult:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Critic returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    scores_raw = data.get("scores", {}) or {}

    def _clamp(v: object) -> int:
        try:
            return max(1, min(5, int(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 3

    scores = CriticScores(
        seo_quality=_clamp(scores_raw.get("seo_quality", 3)),
        clarity=_clamp(scores_raw.get("clarity", 3)),
        technical_accuracy=_clamp(scores_raw.get("technical_accuracy", 3)),
        publish_readiness=_clamp(scores_raw.get("publish_readiness", 3)),
    )

    verdict_raw = str(data.get("verdict", "revise")).lower()
    verdict: Literal["pass", "revise"] = "pass" if verdict_raw == "pass" else "revise"

    # Deterministic override — code enforces the rule, model cannot cheat.
    if not scores.all_pass():
        verdict = "revise"

    return CriticResult(
        verdict=verdict,
        revision_instruction=str(data.get("revision_instruction") or "").strip(),
        scores=scores,
        failures=list(data.get("failures") or []),
    )


# ------------------------------------------------------------------ #
# CriticAgent                                                          #
# ------------------------------------------------------------------ #


class CriticAgent(BaseAgent):
    """LLM-based critic that reviews a BlogJob and returns a pass/revise verdict.

    Extends BaseAgent: reads skills/critic.md as system prompt, uses think()
    for the sole LLM call.  No direct google-genai imports here.

    Args:
        config: BrewPressConfig with google_api_key set.
        model:  Gemini model name.
    """

    SKILL: str | Path = "skills/critic.md"
    TOOLS: list[str] = []  # deterministic checks done by caller; critic is pure LLM

    def review(self, job: BlogJob) -> CriticResult:
        """Evaluate a BlogJob draft and return a structured verdict.

        Args:
            job: BlogJob in any state (DRAFT recommended).

        Returns:
            CriticResult with verdict, scores, failures, and revision_instruction.

        Raises:
            ValueError: GOOGLE_API_KEY not set, or model response cannot be parsed.
        """
        prompt = _build_critic_prompt(job)
        raw = self.think(prompt, temperature=0.2, max_output_tokens=2048, response_schema=_CriticSchema)
        return _parse_critic_response(raw)
