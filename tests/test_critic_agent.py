"""Tests for brewpress.critic_agent — LLM-based post review."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brewpress.critic_agent import (
    PASS_THRESHOLD,
    CriticAgent,
    CriticResult,
    CriticScores,
    _build_critic_prompt,
    _compute_publish_readiness,
    _parse_critic_response,
    _seo_score_to_quality,
)
from brewpress.models import BlogJob

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


def _job(**kwargs) -> BlogJob:
    defaults = dict(
        title="Java 21 Virtual Threads: A Practical Guide",
        meta_description=(
            "Learn how Java 21 virtual threads work and when to use them "
            "in production Spring Boot applications. A hands-on walkthrough."
        ),
        primary_keyword="java 21 virtual threads",
        secondary_keywords=["spring boot", "concurrency", "jvm"],
        draft_body_md=(
            "# Java 21 Virtual Threads\n\n"
            "Java 21 virtual threads change how you think about concurrency.\n\n"
            "## What are virtual threads?\n\n"
            "Virtual threads are lightweight threads managed by the JVM.\n\n"
            "```java\nThread.ofVirtual().start(() -> System.out.println(\"hi\"));\n```\n\n"
            "## When to use them\n\n"
            "Use them for I/O-bound workloads. Not CPU-bound ones.\n"
        ),
        quality_score=72,
        quality_gaps=["missing TL;DR", "intro is thin"],
    )
    defaults.update(kwargs)
    return BlogJob(**defaults)


def _make_agent(response_dict: dict) -> CriticAgent:
    agent = object.__new__(CriticAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client       # BaseAgent attr name
    agent._llm_types = MagicMock()        # BaseAgent attr name
    agent._model = "gemini-2.0-flash"
    agent._config = MagicMock()
    agent._skill_path = Path("skills/critic.md")
    agent._skill_text = None
    return agent


# Rich body with enough words/structure for _compute_publish_readiness to return 4+
_RICH_BODY = (
    "# Java 21 Virtual Threads: A Complete Guide\n\n"
    "Java 21 introduced virtual threads as a production-ready feature that changes how developers "
    "think about concurrency. Unlike platform threads that map one-to-one to OS threads, "
    "virtual threads are managed by the JVM and can scale to millions without memory pressure. "
    "For I/O-bound applications like REST APIs and database-heavy services, this changes everything.\n\n"
    "## What Are Virtual Threads?\n\n"
    "A virtual thread is a lightweight implementation backed by a ForkJoinPool of carrier threads. "
    "When a virtual thread blocks waiting for I/O, the JVM unmounts it from the carrier thread "
    "and parks it. Another virtual thread immediately takes the freed carrier. This means blocking "
    "code runs with the concurrency of non-blocking code, but without the complexity of "
    "reactive programming or CompletableFuture chains.\n\n"
    "```java\n"
    "try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {\n"
    "    IntStream.range(0, 1_000_000).forEach(i ->\n"
    "        executor.submit(() -> fetchFromDatabase(i))\n"
    "    );\n"
    "}\n"
    "```\n\n"
    "## When to Use Virtual Threads\n\n"
    "Virtual threads are ideal for I/O-bound workloads: HTTP client calls, JDBC queries, "
    "file reads, message queue consumption. Spring Boot 3.2+ supports virtual threads natively. "
    "Set spring.threads.virtual.enabled=true in application.properties and your Tomcat executor "
    "automatically uses virtual threads. Each incoming HTTP request runs on its own virtual thread "
    "with no thread pool sizing required. The JVM manages scheduling entirely.\n\n"
    "## When to Avoid Virtual Threads\n\n"
    "Avoid virtual threads for CPU-intensive work. Hashing, compression, image processing, "
    "or any task that burns CPU without blocking gets no benefit from virtual threads. You still "
    "saturate all available cores. Synchronized blocks that contain blocking calls also cause "
    "thread pinning, which degrades performance significantly under load.\n\n"
    "Get started today — virtual threads are production-ready and worth the upgrade.\n"
)

_PASS_RESPONSE = {
    "scores": {
        "seo_quality": 4,
        "clarity": 5,
        "technical_accuracy": 4,
        "publish_readiness": 4,
    },
    "failures": [],
    "verdict": "pass",
    "revision_instruction": "",
}

_REVISE_RESPONSE = {
    "scores": {
        "seo_quality": 3,
        "clarity": 4,
        "technical_accuracy": 4,
        "publish_readiness": 3,
    },
    "failures": [
        "Primary keyword missing from first 100 words.",
        "Meta description is 96 chars — too short.",
    ],
    "verdict": "revise",
    "revision_instruction": (
        "Add 'java 21 virtual threads' to the intro paragraph. "
        "Expand meta description to 130+ chars."
    ),
}


# ------------------------------------------------------------------ #
# CriticScores                                                         #
# ------------------------------------------------------------------ #


def test_all_pass_true_when_all_above_threshold() -> None:
    scores = CriticScores(seo_quality=4, clarity=5, technical_accuracy=4, publish_readiness=4)
    assert scores.all_pass()


def test_all_pass_false_when_any_below_threshold() -> None:
    scores = CriticScores(seo_quality=3, clarity=5, technical_accuracy=4, publish_readiness=4)
    assert not scores.all_pass()


def test_lowest_returns_minimum_dimension() -> None:
    scores = CriticScores(seo_quality=3, clarity=5, technical_accuracy=4, publish_readiness=4)
    dim, val = scores.lowest()
    assert dim == "seo_quality"
    assert val == 3


def test_pass_threshold_default_is_4() -> None:
    assert PASS_THRESHOLD == 4


# ------------------------------------------------------------------ #
# CriticResult                                                         #
# ------------------------------------------------------------------ #


def test_is_pass_true_for_pass_verdict() -> None:
    scores = CriticScores(seo_quality=4, clarity=4, technical_accuracy=4, publish_readiness=4)
    result = CriticResult(verdict="pass", revision_instruction="", scores=scores, failures=[])
    assert result.is_pass()


def test_is_pass_false_for_revise_verdict() -> None:
    scores = CriticScores(seo_quality=3, clarity=4, technical_accuracy=4, publish_readiness=3)
    result = CriticResult(
        verdict="revise", revision_instruction="Fix SEO.", scores=scores, failures=[]
    )
    assert not result.is_pass()


def test_summary_pass_shows_weakest_dim() -> None:
    scores = CriticScores(seo_quality=4, clarity=5, technical_accuracy=4, publish_readiness=4)
    result = CriticResult(verdict="pass", revision_instruction="", scores=scores, failures=[])
    summary = result.summary()
    assert "PASS" in summary
    assert "4/5" in summary


def test_summary_revise_shows_revision() -> None:
    scores = CriticScores(seo_quality=3, clarity=4, technical_accuracy=4, publish_readiness=3)
    result = CriticResult(
        verdict="revise",
        revision_instruction="Add keyword to intro.",
        scores=scores,
        failures=[],
    )
    summary = result.summary()
    assert "REVISE" in summary
    assert "keyword" in summary.lower()


# ------------------------------------------------------------------ #
# _build_critic_prompt                                                 #
# ------------------------------------------------------------------ #


def test_prompt_includes_title() -> None:
    job = _job()
    prompt = _build_critic_prompt(job)
    assert job.title in prompt


def test_prompt_includes_primary_keyword() -> None:
    job = _job()
    prompt = _build_critic_prompt(job)
    assert "java 21 virtual threads" in prompt


def test_prompt_includes_quality_score_when_set() -> None:
    job = _job(quality_score=65)
    prompt = _build_critic_prompt(job)
    assert "65" in prompt


def test_prompt_truncates_long_body() -> None:
    long_body = "x " * 5000
    job = _job(draft_body_md=long_body)
    prompt = _build_critic_prompt(job)
    assert "truncated" in prompt


def test_prompt_includes_key_fields() -> None:
    job = _job()
    prompt = _build_critic_prompt(job)
    assert job.title in prompt
    assert job.primary_keyword in prompt


# ------------------------------------------------------------------ #
# _parse_critic_response                                               #
# ------------------------------------------------------------------ #


def test_parse_pass_response() -> None:
    raw = json.dumps(_PASS_RESPONSE)
    result = _parse_critic_response(raw)
    assert result.verdict == "pass"
    assert result.is_pass()
    assert result.revision_instruction == ""


def test_parse_revise_response() -> None:
    raw = json.dumps(_REVISE_RESPONSE)
    result = _parse_critic_response(raw)
    assert result.verdict == "revise"
    assert len(result.failures) == 2
    assert result.revision_instruction != ""


def test_parse_clamps_score_out_of_range() -> None:
    resp = {**_PASS_RESPONSE, "scores": {
        "seo_quality": 99, "clarity": -1,
        "technical_accuracy": 4, "publish_readiness": 4,
    }}
    result = _parse_critic_response(json.dumps(resp))
    assert result.scores.seo_quality == 5
    assert result.scores.clarity == 1


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_critic_response("not json")


def test_parse_overrides_pass_verdict_when_scores_low() -> None:
    """If model says pass but scores disagree, deterministic rule wins."""
    resp = {
        **_PASS_RESPONSE,
        "scores": {
            "seo_quality": 2,  # below threshold
            "clarity": 5,
            "technical_accuracy": 5,
            "publish_readiness": 5,
        },
        "verdict": "pass",  # model says pass but score is 2
    }
    result = _parse_critic_response(json.dumps(resp))
    assert result.verdict == "revise"


def test_parse_handles_missing_failures_gracefully() -> None:
    resp = {**_PASS_RESPONSE}
    resp.pop("failures", None)
    result = _parse_critic_response(json.dumps(resp))
    assert result.failures == []


# ------------------------------------------------------------------ #
# CriticAgent construction                                             #
# ------------------------------------------------------------------ #


def test_agent_raises_without_api_key() -> None:
    from brewpress.config import BrewPressConfig

    cfg = BrewPressConfig()
    agent = CriticAgent(cfg)
    # think() is the only place GOOGLE_API_KEY is enforced (lazy LLM init)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        agent.think("test")


# ------------------------------------------------------------------ #
# CriticAgent.review                                                   #
# ------------------------------------------------------------------ #


def test_review_returns_pass_result() -> None:
    agent = _make_agent(_PASS_RESPONSE)
    # Use rich body so _compute_publish_readiness returns 4+ (deterministic override)
    job = _job(draft_body_md=_RICH_BODY, cta="Get started today.")
    result = agent.review(job)
    assert isinstance(result, CriticResult)
    assert result.is_pass()


def test_review_returns_revise_result() -> None:
    agent = _make_agent(_REVISE_RESPONSE)
    result = agent.review(_job())
    assert not result.is_pass()
    assert result.verdict == "revise"


def test_review_calls_model_with_job_title() -> None:
    agent = _make_agent(_PASS_RESPONSE)
    job = _job()
    agent.review(job)
    call = agent._llm_client.models.generate_content.call_args
    contents = call[1].get("contents") or call[0][1]
    assert job.title in contents


def test_review_raises_on_bad_json() -> None:
    agent = _make_agent({})
    agent._llm_client.models.generate_content.return_value.text = "not json"
    with pytest.raises(ValueError, match="invalid JSON"):
        agent.review(_job())


def test_review_overrides_seo_quality_when_job_has_seo_score() -> None:
    """When job.seo_score is set, seo_quality is overridden deterministically."""
    agent = _make_agent(_PASS_RESPONSE)
    # seo_score=40 → _seo_score_to_quality → 2 (below threshold)
    job = _job(seo_score=40, draft_body_md=_RICH_BODY, cta="Get started today.")
    result = agent.review(job)
    assert result.scores.seo_quality == 2
    assert result.verdict == "revise"  # seo_quality=2 forces revise


def test_review_overrides_publish_readiness_from_content() -> None:
    """publish_readiness is always overridden by _compute_publish_readiness."""
    agent = _make_agent(_PASS_RESPONSE)
    # _PASS_RESPONSE has publish_readiness=4, but rich body → computed=4 or 5
    job = _job(draft_body_md=_RICH_BODY, cta="Get started today.")
    result = agent.review(job)
    assert result.scores.publish_readiness >= 4


def test_review_thin_body_forces_revise_via_publish_readiness() -> None:
    """A minimal body → publish_readiness=1 → verdict overridden to revise."""
    agent = _make_agent(_PASS_RESPONSE)
    job = _job(draft_body_md="# Thin\n\nShort post.")
    result = agent.review(job)
    assert result.scores.publish_readiness < 4
    assert result.verdict == "revise"


# ------------------------------------------------------------------ #
# _seo_score_to_quality                                               #
# ------------------------------------------------------------------ #


def test_seo_score_to_quality_85_maps_to_5() -> None:
    assert _seo_score_to_quality(85) == 5


def test_seo_score_to_quality_90_maps_to_5() -> None:
    assert _seo_score_to_quality(90) == 5


def test_seo_score_to_quality_70_maps_to_4() -> None:
    assert _seo_score_to_quality(70) == 4


def test_seo_score_to_quality_55_maps_to_3() -> None:
    assert _seo_score_to_quality(55) == 3


def test_seo_score_to_quality_40_maps_to_2() -> None:
    assert _seo_score_to_quality(40) == 2


def test_seo_score_to_quality_30_maps_to_1() -> None:
    assert _seo_score_to_quality(30) == 1


# ------------------------------------------------------------------ #
# _compute_publish_readiness                                          #
# ------------------------------------------------------------------ #


def test_compute_publish_readiness_rich_body_scores_4() -> None:
    job = _job(draft_body_md=_RICH_BODY, cta="Get started today.")
    score = _compute_publish_readiness(job)
    assert score >= 4


def test_compute_publish_readiness_thin_body_scores_1() -> None:
    job = _job(draft_body_md="# Title\n\nOne sentence.")
    score = _compute_publish_readiness(job)
    assert score == 1


def test_compute_publish_readiness_uses_cta_field() -> None:
    """cta field on BlogJob counts as has_cta signal."""
    body = "# Post\n\n" + "Word " * 360 + "\n\n## Section\n\nContent."
    job = _job(draft_body_md=body, cta="Subscribe for more.")
    score = _compute_publish_readiness(job)
    assert score >= 4


def test_compute_publish_readiness_medium_body_scores_3() -> None:
    body = "# Post\n\n" + "Content word " * 20 + "\n"  # ~40 words → score 2
    job = _job(draft_body_md=body)
    score = _compute_publish_readiness(job)
    assert score <= 2
