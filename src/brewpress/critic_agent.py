"""Critic Agent — LLM-based post review and revision gating.

Implements the Generator + Critic loop pattern from the ADK spec.

The critic evaluates a BlogJob draft on four dimensions and returns a
structured verdict. When the verdict is "revise", the caller should feed
``revision_instruction`` directly into ``ReviewGate.revise()`` so the
draft pipeline re-runs with targeted guidance.

Pipeline position:
    BlogJob (DRAFT)  →  CriticAgent.review()  →  CriticResult
                                    │
                           verdict == "revise"
                                    │
                    ReviewGate.revise(revision_instruction)
                                    │
                         BlogJob (DRAFT, revised)  →  DraftAgent

Scoring:
    Each dimension is scored 1–5 by the model.
    verdict = "pass"   when ALL scores >= PASS_THRESHOLD (default 4)
    verdict = "revise" when ANY score < PASS_THRESHOLD

Revision instruction:
    A concise, actionable string (≤ 200 chars) summarising all changes
    needed in one go — suitable for direct use as the revise() argument.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

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
# Critic system prompt                                                 #
# ------------------------------------------------------------------ #

_CRITIC_SYSTEM_PROMPT = """\
You are a senior technical editor evaluating a blog post draft.
Your job is to give an honest, specific, actionable review — not flattery.

Scoring dimensions (1–5 each):
  seo_quality:         keyword placement, title/meta length, heading hierarchy
  clarity:             readability, paragraph length, active voice, flow
  technical_accuracy:  code correctness, no invented facts, accurate claims
  publish_readiness:   hook quality, conclusion, overall polish, CTA present

Score 5: excellent, no changes needed
Score 4: good, minor polishing only
Score 3: needs work in this area
Score 2: significant problems
Score 1: unacceptable, must rewrite

Rules:
- verdict = "pass"   when ALL scores >= 4
- verdict = "revise" when ANY score < 4
- revision_instruction MUST be specific (cite headings, lines, or sections)
- revision_instruction must be 1-3 sentences, ≤ 200 characters
- failures list concrete problems, not generic observations

Do NOT fabricate metrics. Do NOT guarantee rankings.
"""


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
        f"**Body:**\n---\n{body_preview}\n---\n\n"
        "Return a JSON object:\n"
        "{\n"
        '  "scores": {\n'
        '    "seo_quality": <1-5>,\n'
        '    "clarity": <1-5>,\n'
        '    "technical_accuracy": <1-5>,\n'
        '    "publish_readiness": <1-5>\n'
        "  },\n"
        '  "failures": ["<specific issue>", ...],\n'
        '  "verdict": "pass" | "revise",\n'
        '  "revision_instruction": "<actionable instruction or empty string>"\n'
        "}"
    )


# ------------------------------------------------------------------ #
# Response parsing                                                     #
# ------------------------------------------------------------------ #

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


def _parse_critic_response(raw: str) -> CriticResult:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Critic returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    scores_raw = data.get("scores", {}) or {}
    # Clamp scores to [1, 5] so a misbehaving model doesn't hard-fail Pydantic.
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

    # Override verdict with deterministic rule — model can be overridden if scores say so.
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

_DEFAULT_MODEL = "gemini-2.0-flash"


class CriticAgent:
    """LLM-based critic that reviews a BlogJob and returns a pass/revise verdict.

    Args:
        config: BrewPressConfig with google_api_key set.
        model:  Gemini model name.

    Example:
        config = load_config(required=("GOOGLE_API_KEY",))
        critic = CriticAgent(config)
        result = critic.review(job)
        if not result.is_pass():
            job = gate.revise(result.revision_instruction)
    """

    def __init__(self, config: BrewPressConfig, model: str = _DEFAULT_MODEL) -> None:
        if not config.google_api_key:
            raise ValueError(
                "CriticAgent requires GOOGLE_API_KEY. "
                "Set the environment variable and retry."
            )
        from google import genai
        from google.genai import types as _types

        self._client = genai.Client(api_key=config.google_api_key)
        self._model = model
        self._types = _types

    def review(self, job: BlogJob) -> CriticResult:
        """Evaluate a BlogJob draft and return a structured verdict.

        Args:
            job: BlogJob in any state (DRAFT or REVIEWED recommended).

        Returns:
            CriticResult with verdict, scores, failures, and revision_instruction.

        Raises:
            ValueError: If the model response cannot be parsed.
        """
        prompt = _build_critic_prompt(job)

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=_CRITIC_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,  # low temperature for consistent scoring
                max_output_tokens=1024,
            ),
        )

        raw = response.text or ""
        return _parse_critic_response(raw)
