"""Blog Boost Assistant — content optimization agent for BrewPress.

Analyzes a blog post draft (or any Markdown content) and returns structured
SEO feedback, structure improvements, and engagement tips using Gemini Flash.

ADK mapping:
    task_type  →  BlogBoostAgent.run(task=...)
    output     →  BoostResult (Pydantic model, JSON-serializable)

Supported task types:
    seo_audit           — full SEO analysis of the provided content
    rewrite             — clarity/SEO/concise rewrite of the content
    title_suggestions   — 5 alternative title options
    meta_description    — generate or improve the meta description
    content_feedback    — constructive editorial feedback
    topic_ideas         — suggest related blog topics
    internal_linking    — identify internal linking opportunities
    engagement_message  — draft a contributor invite or feedback message

Pipeline position:
    BlogJob (DRAFT or REVIEWED)  →  BlogBoostAgent.run()  →  BoostResult
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from brewpress.config import BrewPressConfig

# ------------------------------------------------------------------ #
# Version                                                              #
# ------------------------------------------------------------------ #

SYSTEM_PROMPT_VERSION = "v1.0"

# ------------------------------------------------------------------ #
# Task type                                                            #
# ------------------------------------------------------------------ #

TaskType = Literal[
    "seo_audit",
    "rewrite",
    "title_suggestions",
    "meta_description",
    "content_feedback",
    "topic_ideas",
    "internal_linking",
    "engagement_message",
]

# ------------------------------------------------------------------ #
# Input / Output models                                                #
# ------------------------------------------------------------------ #


class BoostRequest(BaseModel):
    """Input to the Blog Boost Assistant."""

    task_type: TaskType
    content: str = Field(default="", description="Blog post body (Markdown or plain text).")
    keywords: list[str] = Field(default_factory=list, description="Target keywords.")
    target_audience: str = Field(
        default="mid-to-senior backend developers",
        description="Intended readership.",
    )
    tone: str = Field(
        default="professional, friendly, developer-focused",
        description="Desired writing tone.",
    )
    word_count: int | None = Field(
        default=None,
        description="Target word count for rewrites.",
        ge=100,
    )
    format: Literal["blog", "email", "social"] = Field(
        default="blog",
        description="Output format for engagement messages.",
    )


class SEOSuggestions(BaseModel):
    keywords_used: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    title_feedback: str = ""
    meta_description: str = ""
    readability_score: str = ""


class BoostResult(BaseModel):
    """Structured output from the Blog Boost Assistant."""

    task_type: TaskType
    optimized_content: str = ""
    seo_suggestions: SEOSuggestions = Field(default_factory=SEOSuggestions)
    structure_improvements: list[str] = Field(default_factory=list)
    engagement_tips: list[str] = Field(default_factory=list)
    raw_model_output: str = Field(
        default="",
        description="Unprocessed model response for debugging.",
        exclude=True,
    )

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(exclude={"raw_model_output"})


# ------------------------------------------------------------------ #
# System prompt                                                        #
# ------------------------------------------------------------------ #

_SYSTEM_PROMPT = f"""\
You are Blog Boost Assistant ({SYSTEM_PROMPT_VERSION}), an SEO-focused assistant \
for a developer-focused technical blog.

Your responsibilities:
- Improve blog content for clarity, structure, and readability
- Apply modern, ethical SEO best practices
- Provide actionable, specific suggestions (not generic advice)
- Maintain a professional but friendly, community-oriented tone

SEO Guidelines:
- Prioritize human readability over keyword density
- Use natural keyword placement (avoid stuffing)
- Ensure proper heading hierarchy (H1 exactly once, H2 for sections, H3 for sub-points)
- Optimize titles (50–60 chars) and meta descriptions (120–160 chars)
- Primary keyword should appear in the first 100 words

Writing Standards:
- Short paragraphs (2–3 sentences). One idea per paragraph.
- Active voice. No filler phrases like "In today's fast-paced world".
- Code blocks for all code, shell commands, and expected output (with language hint).
- Developer tone: confident, direct, technically exact.

Communication Style:
- Be constructive and supportive
- Explain "why" behind suggestions when useful
- Avoid jargon unless relevant to developers

Constraints:
- Do NOT claim guaranteed rankings
- Do NOT use outdated SEO tactics
- Do NOT fabricate data or metrics
- Output MUST follow the required JSON schema exactly.
"""

# ------------------------------------------------------------------ #
# Per-task prompt builders                                             #
# ------------------------------------------------------------------ #


def _seo_audit_prompt(req: BoostRequest) -> str:
    kw = ", ".join(req.keywords) if req.keywords else "none specified"
    return (
        f"Perform a full SEO audit of the following blog post draft.\n"
        f"Target keywords: {kw}\n"
        f"Target audience: {req.target_audience}\n\n"
        f"Content:\n---\n{req.content}\n---\n\n"
        "Return a JSON object matching this schema:\n"
        "{\n"
        '  "optimized_content": "",\n'
        '  "seo_suggestions": {\n'
        '    "keywords_used": [],\n'
        '    "missing_keywords": [],\n'
        '    "title_feedback": "",\n'
        '    "meta_description": "",\n'
        '    "readability_score": ""\n'
        "  },\n"
        '  "structure_improvements": [],\n'
        '  "engagement_tips": []\n'
        "}"
    )


def _rewrite_prompt(req: BoostRequest) -> str:
    kw = ", ".join(req.keywords) if req.keywords else "none specified"
    wc = f" Target word count: ~{req.word_count}." if req.word_count else ""
    return (
        f"Rewrite the following blog post for clarity and SEO.{wc}\n"
        f"Target keywords: {kw}\n"
        f"Tone: {req.tone}\n"
        f"Audience: {req.target_audience}\n\n"
        f"Content:\n---\n{req.content}\n---\n\n"
        "Return a JSON object with:\n"
        '{ "optimized_content": "<full rewritten post in Markdown>", '
        '"seo_suggestions": {...}, "structure_improvements": [], "engagement_tips": [] }'
    )


def _title_suggestions_prompt(req: BoostRequest) -> str:
    kw = ", ".join(req.keywords) if req.keywords else "none specified"
    return (
        "Suggest 5 SEO-optimized title alternatives for this post.\n"
        f"Primary keyword(s): {kw}\n\n"
        f"Content summary:\n---\n{req.content[:1500]}\n---\n\n"
        "Rules: each title 50–60 characters, keyword near the front, no clickbait.\n"
        "Return JSON: "
        '{ "optimized_content": "<titles as a numbered Markdown list>", '
        '"seo_suggestions": {"title_feedback": "<why these work>"}, '
        '"structure_improvements": [], "engagement_tips": [] }'
    )


def _meta_description_prompt(req: BoostRequest) -> str:
    kw = ", ".join(req.keywords) if req.keywords else "none specified"
    return (
        "Write or improve the meta description for this post.\n"
        f"Keywords: {kw}\n\n"
        f"Content summary:\n---\n{req.content[:1500]}\n---\n\n"
        "Rules: 120–160 characters, includes primary keyword, entices clicks without clickbait.\n"
        "Return JSON: "
        '{ "optimized_content": "", "seo_suggestions": '
        '{"meta_description": "<the meta description>"}, '
        '"structure_improvements": [], "engagement_tips": [] }'
    )


def _content_feedback_prompt(req: BoostRequest) -> str:
    return (
        "Provide constructive editorial feedback on this blog post.\n"
        f"Audience: {req.target_audience}\n\n"
        f"Content:\n---\n{req.content}\n---\n\n"
        "Be specific, friendly, and actionable. Cite line-level issues where relevant.\n"
        "Return JSON: "
        '{ "optimized_content": "", "seo_suggestions": {}, '
        '"structure_improvements": ["<specific suggestion>", ...], '
        '"engagement_tips": ["<specific tip>", ...] }'
    )


def _topic_ideas_prompt(req: BoostRequest) -> str:
    kw = ", ".join(req.keywords) if req.keywords else "none specified"
    ctx = req.content[:800] if req.content else "developer-focused technical blog"
    return (
        f"Suggest 7 blog topic ideas for a {req.target_audience} audience.\n"
        f"Seed keywords: {kw}\n"
        f"Blog context: {ctx}\n\n"
        "For each: topic title, angle, primary keyword, and one-line rationale.\n"
        "Return JSON: "
        '{ "optimized_content": "<topics as Markdown list>", '
        '"seo_suggestions": {}, "structure_improvements": [], "engagement_tips": [] }'
    )


def _internal_linking_prompt(req: BoostRequest) -> str:
    return (
        "Identify internal linking opportunities in this post.\n"
        "For each opportunity: anchor text, where to place it, and content type to link.\n\n"
        f"Content:\n---\n{req.content}\n---\n\n"
        "Return JSON: "
        '{ "optimized_content": "", "seo_suggestions": {}, '
        '"structure_improvements": ["<linking suggestion>", ...], "engagement_tips": [] }'
    )


def _engagement_message_prompt(req: BoostRequest) -> str:
    fmt = req.format
    return (
        f"Draft a {fmt} message to invite a contributor to submit or improve posts.\n"
        f"Tone: {req.tone}\n"
        f"Audience: {req.target_audience}\n\n"
        "The message should be friendly, specific, non-judgmental, and community-driven.\n"
        "Return JSON: "
        '{ "optimized_content": "<the message>", '
        '"seo_suggestions": {}, "structure_improvements": [], '
        '"engagement_tips": ["<follow-up tip>", ...] }'
    )


_PROMPT_BUILDERS = {
    "seo_audit": _seo_audit_prompt,
    "rewrite": _rewrite_prompt,
    "title_suggestions": _title_suggestions_prompt,
    "meta_description": _meta_description_prompt,
    "content_feedback": _content_feedback_prompt,
    "topic_ideas": _topic_ideas_prompt,
    "internal_linking": _internal_linking_prompt,
    "engagement_message": _engagement_message_prompt,
}

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


def _parse_boost_response(raw: str, task_type: TaskType) -> BoostResult:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {exc}\n\nRaw:\n{raw}") from exc

    seo_raw = data.get("seo_suggestions", {}) or {}
    seo = SEOSuggestions(
        keywords_used=seo_raw.get("keywords_used") or [],
        missing_keywords=seo_raw.get("missing_keywords") or [],
        title_feedback=seo_raw.get("title_feedback") or "",
        meta_description=seo_raw.get("meta_description") or "",
        readability_score=seo_raw.get("readability_score") or "",
    )

    return BoostResult(
        task_type=task_type,
        optimized_content=data.get("optimized_content") or "",
        seo_suggestions=seo,
        structure_improvements=data.get("structure_improvements") or [],
        engagement_tips=data.get("engagement_tips") or [],
        raw_model_output=raw,
    )


# ------------------------------------------------------------------ #
# BlogBoostAgent                                                       #
# ------------------------------------------------------------------ #

_DEFAULT_MODEL = "gemini-2.0-flash"


class BlogBoostAgent:
    """Content optimization agent for blog posts.

    Args:
        config: BrewPressConfig with google_api_key set.
        model:  Gemini model name.

    Example:
        config = load_config(required=("GOOGLE_API_KEY",))
        agent = BlogBoostAgent(config)
        result = agent.run(BoostRequest(task_type="seo_audit", content=body, keywords=["k8s"]))
        print(result.seo_suggestions.meta_description)
    """

    def __init__(self, config: BrewPressConfig, model: str = _DEFAULT_MODEL) -> None:
        if not config.google_api_key:
            raise ValueError(
                "BlogBoostAgent requires GOOGLE_API_KEY. "
                "Set the environment variable and retry."
            )
        from google import genai
        from google.genai import types as _types

        self._client = genai.Client(api_key=config.google_api_key)
        self._model = model
        self._types = _types

    def run(self, request: BoostRequest) -> BoostResult:
        """Run a blog optimization task.

        Args:
            request: BoostRequest specifying the task and content.

        Returns:
            BoostResult with structured suggestions and optimized content.

        Raises:
            ValueError:  If the model response cannot be parsed.
            KeyError:    If task_type is not recognized (should not happen with typed input).
        """
        builder = _PROMPT_BUILDERS[request.task_type]
        prompt = builder(request)

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )

        raw = response.text or ""
        return _parse_boost_response(raw, request.task_type)
