"""Tests for brewpress.seo_agent — SEOAgent title, meta, and keyword optimization."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brewpress.models import BlogJob
from brewpress.seo_agent import SEOAgent, _build_prompt, _SEO_FAST_PATH_THRESHOLD


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _job(**kwargs) -> BlogJob:
    defaults = dict(
        title="Java 21 Virtual Threads: A Practical Guide",
        meta_description=(
            "Learn how Java 21 virtual threads change concurrency in Spring Boot. "
            "A practical guide with real examples for production developers."
        ),
        primary_keyword="java 21 virtual threads",
        secondary_keywords=["spring boot", "concurrency", "jvm"],
        draft_body_md=(
            "# Java 21 Virtual Threads\n\n"
            "Java 21 virtual threads change how you think about concurrency.\n\n"
            "## What are virtual threads?\n\n"
            "Lightweight JVM-managed threads.\n\n"
            "## When to use them\n\nI/O-bound workloads only.\n"
        ),
    )
    defaults.update(kwargs)
    return BlogJob(**defaults)


_SEO_PASS_RESULT = {
    "score": 90,
    "checks": {
        "title": {"in_range": True, "char_count": 52},
        "meta": {"in_range": True, "char_count": 145},
        "keywords": {"missing": []},
        "headings": {"issues": []},
    },
}

_SEO_FAIL_RESULT = {
    "score": 62,
    "checks": {
        "title": {"in_range": False, "char_count": 30},
        "meta": {"in_range": False, "char_count": 90},
        "keywords": {"missing": ["virtual threads"]},
        "headings": {"issues": ["H1 missing primary keyword"]},
    },
}

_LLM_IMPROVED = {
    "title": "Java 21 Virtual Threads: Complete Developer Guide (2024)",
    "meta_description": (
        "Master Java 21 virtual threads with this practical guide. "
        "Learn when to use them, how they compare to platform threads, "
        "and see real Spring Boot examples. Updated for JDK 21."
    ),
    "draft_body_md": (
        "# Java 21 Virtual Threads: Complete Guide\n\n"
        "Java 21 virtual threads are the biggest concurrency change in years.\n\n"
        "## What are Java 21 virtual threads?\n\n"
        "Lightweight, JVM-managed threads for I/O-bound work."
    ),
}


def _make_agent(seo_tool_result: dict, llm_response: str = "") -> SEOAgent:
    agent = object.__new__(SEOAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = llm_response
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client
    agent._llm_types = MagicMock()
    agent._model = "gemini-2.0-flash"
    agent._config = MagicMock()
    agent._skill_path = Path("skills/seo.md")
    agent._skill_text = "You are an SEO agent."
    agent.use = MagicMock(return_value=seo_tool_result)  # type: ignore[method-assign]
    return agent


# ------------------------------------------------------------------ #
# _build_prompt                                                        #
# ------------------------------------------------------------------ #

def test_build_prompt_includes_score() -> None:
    prompt = _build_prompt(_job(), _SEO_FAIL_RESULT)
    assert "62" in prompt


def test_build_prompt_includes_title_length_issue() -> None:
    prompt = _build_prompt(_job(), _SEO_FAIL_RESULT)
    assert "Title" in prompt
    assert "30" in prompt


def test_build_prompt_includes_meta_length_issue() -> None:
    prompt = _build_prompt(_job(), _SEO_FAIL_RESULT)
    assert "Meta" in prompt
    assert "90" in prompt


def test_build_prompt_includes_missing_keywords() -> None:
    prompt = _build_prompt(_job(), _SEO_FAIL_RESULT)
    assert "virtual threads" in prompt


def test_build_prompt_includes_heading_issues() -> None:
    prompt = _build_prompt(_job(), _SEO_FAIL_RESULT)
    assert "H1 missing primary keyword" in prompt


def test_build_prompt_truncates_long_body() -> None:
    long_body = "x " * 5000
    job = _job(draft_body_md=long_body)
    prompt = _build_prompt(job, _SEO_FAIL_RESULT)
    assert "truncated" in prompt


def test_build_prompt_no_issues_text_when_score_high() -> None:
    prompt = _build_prompt(_job(), _SEO_PASS_RESULT)
    assert "General SEO improvements needed" in prompt


# ------------------------------------------------------------------ #
# SEOAgent.optimize — fast path (score >= threshold, first pass)       #
# ------------------------------------------------------------------ #

def test_fast_path_threshold_is_85() -> None:
    assert _SEO_FAST_PATH_THRESHOLD == 85


def test_optimize_fast_path_skips_llm_when_score_high_first_pass() -> None:
    agent = _make_agent(seo_tool_result={**_SEO_PASS_RESULT, "score": 90})
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    assert result.seo_score == 90  # seo_score stamped even on fast path
    assert result.title == job.title  # content unchanged
    agent._llm_client.models.generate_content.assert_not_called()


def test_optimize_fast_path_boundary_at_threshold() -> None:
    agent = _make_agent(seo_tool_result={**_SEO_PASS_RESULT, "score": 85})
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    assert result.seo_score == 85


def test_optimize_calls_llm_when_score_below_threshold() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result={**_SEO_FAIL_RESULT, "score": 62}, llm_response=llm_response)
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    agent._llm_client.models.generate_content.assert_called_once()
    assert result.title == _LLM_IMPROVED["title"]


def test_optimize_calls_llm_on_revision_even_if_score_high() -> None:
    """Revision passes always call LLM — WriterAgent rewrites can introduce SEO regressions."""
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result={**_SEO_PASS_RESULT, "score": 92}, llm_response=llm_response)
    job = _job(revision_attempt=1)  # revision pass
    result = agent.optimize(job)
    agent._llm_client.models.generate_content.assert_called_once()


# ------------------------------------------------------------------ #
# SEOAgent.optimize — LLM path                                         #
# ------------------------------------------------------------------ #

def test_optimize_updates_title_from_llm() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    result = agent.optimize(_job(revision_attempt=0))
    assert result.title == _LLM_IMPROVED["title"]


def test_optimize_updates_meta_description_from_llm() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    result = agent.optimize(_job(revision_attempt=0))
    assert result.meta_description == _LLM_IMPROVED["meta_description"]


def test_optimize_updates_body_from_llm() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    result = agent.optimize(_job(revision_attempt=0))
    assert result.draft_body_md == _LLM_IMPROVED["draft_body_md"]


def test_optimize_returns_new_job_object_not_same() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    assert result is not job


def test_optimize_preserves_fields_not_in_llm_response() -> None:
    partial_llm = {"title": "New Title Only"}
    llm_response = json.dumps(partial_llm)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    # title updated
    assert result.title == "New Title Only"
    # fields not in response preserved
    assert result.primary_keyword == job.primary_keyword
    assert result.secondary_keywords == job.secondary_keywords


def test_optimize_raises_on_invalid_json() -> None:
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response="not json")
    with pytest.raises(ValueError, match="invalid JSON"):
        agent.optimize(_job(revision_attempt=0))


def test_optimize_returns_unchanged_job_when_llm_returns_empty_updates() -> None:
    llm_response = json.dumps({"title": "", "meta_description": "", "draft_body_md": ""})
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    job = _job(revision_attempt=0)
    result = agent.optimize(job)
    # seo_score stamped; content fields preserved
    assert result.seo_score == _SEO_FAIL_RESULT["score"]
    assert result.title == job.title


def test_optimize_passes_correct_kwargs_to_seo_tool() -> None:
    llm_response = json.dumps(_LLM_IMPROVED)
    agent = _make_agent(seo_tool_result=_SEO_FAIL_RESULT, llm_response=llm_response)
    job = _job(revision_attempt=0)
    agent.optimize(job)
    call_kwargs = agent.use.call_args[1]  # type: ignore[union-attr]
    assert call_kwargs.get("title") == job.title
    assert call_kwargs.get("primary_keyword") == job.primary_keyword
    assert call_kwargs.get("secondary_keywords") == job.secondary_keywords
