"""Tests for brewpress.critic_agent — LLM-based post review."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brewpress.critic_agent import (
    PASS_THRESHOLD,
    CriticAgent,
    CriticResult,
    CriticScores,
    _build_critic_prompt,
    _parse_critic_response,
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
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()
    return agent


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


def test_prompt_includes_json_schema() -> None:
    job = _job()
    prompt = _build_critic_prompt(job)
    assert "seo_quality" in prompt
    assert "verdict" in prompt


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
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        CriticAgent(cfg)


# ------------------------------------------------------------------ #
# CriticAgent.review                                                   #
# ------------------------------------------------------------------ #


def test_review_returns_pass_result() -> None:
    agent = _make_agent(_PASS_RESPONSE)
    result = agent.review(_job())
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
    call = agent._client.models.generate_content.call_args
    contents = call[1].get("contents") or call[0][1]
    assert job.title in contents


def test_review_raises_on_bad_json() -> None:
    agent = object.__new__(CriticAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "not json"
    mock_client.models.generate_content.return_value = mock_resp
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.review(_job())
