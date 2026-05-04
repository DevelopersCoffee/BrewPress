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


def _seo_score_to_quality(score: int) -> int:
    """Map seo.full 0–100 score to CriticScores.seo_quality 1–5."""
    if score >= 85:
        return 5
    if score >= 70:
        return 4
    if score >= 55:
        return 3
    if score >= 40:
        return 2
    return 1


def _compute_publish_readiness(job: BlogJob) -> int:
    """Compute publish readiness (1–5) from content signals in draft_body_md."""
    body = job.draft_body_md
    words = len(body.split())
    headings = sum(1 for line in body.splitlines() if line.startswith("#"))
    code_blocks = body.count("```") // 2
    has_cta = bool(job.cta) or any(
        phrase in body.lower()
        for phrase in (
            "follow", "subscribe", "check out", "learn more",
            "get started", "try it", "give it a try", "let me know",
        )
    )

    if words >= 600 and has_cta and (code_blocks >= 1 or headings >= 3):
        return 5
    if words >= 200 and (has_cta or code_blocks >= 1) and headings >= 2:
        return 4
    if words >= 200:
        return 3
    if words >= 80:
        return 2
    return 1


def _parse_critic_response(raw: str) -> CriticResult:
    try:
        data = json.loads(raw)
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
        result = _parse_critic_response(raw)

        # Deterministic overrides — code enforces quality signals the LLM can't reliably measure.
        score_updates: dict[str, int] = {
            "publish_readiness": _compute_publish_readiness(job),
        }
        if job.seo_score is not None:
            score_updates["seo_quality"] = _seo_score_to_quality(job.seo_score)

        updated_scores = result.scores.model_copy(update=score_updates)
        verdict = result.verdict
        if not updated_scores.all_pass():
            verdict = "revise"

        return CriticResult(
            verdict=verdict,
            revision_instruction=result.revision_instruction,
            scores=updated_scores,
            failures=result.failures,
        )
