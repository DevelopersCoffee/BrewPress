"""Tests for brewpress.writer_agent — WriterAgent draft generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brewpress.config import BrewPressConfig
from brewpress.models import BlogJob
from brewpress.work_ingestion import WorkContext
from brewpress.writer_agent import WriterAgent, _build_prompt, _extract_json


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _ctx(**kwargs) -> WorkContext:
    defaults = dict(
        topic="Java 21 Virtual Threads",
        notes="",
        diff=None,
        pr_url=None,
        commands=[],
        is_code_post=False,
    )
    defaults.update(kwargs)
    return WorkContext(**defaults)


_VALID_RESPONSE = {
    "title": "Java 21 Virtual Threads: A Developer Guide",
    "slug": "java-21-virtual-threads",
    "meta_description": (
        "Learn how Java 21 virtual threads work and when to use them "
        "in production Spring Boot applications. Practical examples included."
    ),
    "excerpt": "A hands-on guide to Java 21 virtual threads for Spring Boot developers.",
    "primary_keyword": "java 21 virtual threads",
    "secondary_keywords": ["spring boot", "concurrency", "jvm"],
    "outline": ["Introduction", "What are virtual threads?", "When to use them"],
    "draft_body_md": (
        "# Java 21 Virtual Threads\n\n"
        "Virtual threads are lightweight, managed by the JVM.\n\n"
        "## Use cases\n\nI/O-bound workloads benefit most.\n"
    ),
    "hook": "The old way of concurrency is about to change.",
    "cta": "Try virtual threads in your next Spring Boot project.",
    "is_single_topic": True,
    "quality_score": 78,
    "quality_gaps": ["missing TL;DR"],
}


def _make_agent(response_dict: dict) -> WriterAgent:
    agent = object.__new__(WriterAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client
    agent._llm_types = MagicMock()
    agent._model = "gemini-2.0-flash"
    agent._config = MagicMock()
    agent._skill_path = Path("skills/draft.md")
    agent._skill_text = "You are a writer."
    return agent


# ------------------------------------------------------------------ #
# _extract_json                                                        #
# ------------------------------------------------------------------ #

def test_extract_json_plain_object() -> None:
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_strips_markdown_fence() -> None:
    raw = '```json\n{"a": 1}\n```'
    result = _extract_json(raw)
    assert result.startswith("{")


def test_extract_json_strips_bom() -> None:
    raw = '\ufeff{"a": 1}'
    result = _extract_json(raw)
    assert result.startswith("{")


def test_extract_json_finds_embedded_json() -> None:
    raw = "Some text before { \"a\": 1 } after"
    result = _extract_json(raw)
    assert "a" in result


# ------------------------------------------------------------------ #
# _build_prompt                                                        #
# ------------------------------------------------------------------ #

def test_build_prompt_includes_topic() -> None:
    ctx = _ctx(topic="Rust async programming")
    prompt = _build_prompt(ctx, "")
    assert "Rust async programming" in prompt


def test_build_prompt_includes_notes_when_present() -> None:
    ctx = _ctx(notes="Focus on tokio runtime")
    prompt = _build_prompt(ctx, "")
    assert "tokio" in prompt


def test_build_prompt_includes_revision_instruction_when_present() -> None:
    ctx = _ctx()
    prompt = _build_prompt(ctx, "Add more code examples.")
    assert "REVISION" in prompt
    assert "Add more code examples" in prompt


def test_build_prompt_includes_pr_url_when_present() -> None:
    ctx = _ctx(pr_url="https://github.com/org/repo/pull/42")
    prompt = _build_prompt(ctx, "")
    assert "https://github.com/org/repo/pull/42" in prompt


def test_build_prompt_no_revision_section_when_empty() -> None:
    ctx = _ctx()
    prompt = _build_prompt(ctx, "")
    assert "REVISION" not in prompt


# ------------------------------------------------------------------ #
# WriterAgent.generate                                                 #
# ------------------------------------------------------------------ #

def test_generate_returns_blog_job() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = agent.generate(_ctx())
    assert isinstance(job, BlogJob)


def test_generate_populates_title() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = agent.generate(_ctx())
    assert job.title == "Java 21 Virtual Threads: A Developer Guide"


def test_generate_populates_primary_keyword() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = agent.generate(_ctx())
    assert job.primary_keyword == "java 21 virtual threads"


def test_generate_populates_quality_score() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = agent.generate(_ctx())
    assert job.quality_score == 78


def test_generate_populates_quality_gaps() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = agent.generate(_ctx())
    assert "missing TL;DR" in job.quality_gaps


def test_generate_raises_on_multi_topic_without_force() -> None:
    resp = {**_VALID_RESPONSE, "is_single_topic": False}
    agent = _make_agent(resp)
    with pytest.raises(ValueError, match="multi-topic"):
        agent.generate(_ctx(), force=False)


def test_generate_allows_multi_topic_with_force() -> None:
    resp = {**_VALID_RESPONSE, "is_single_topic": False}
    agent = _make_agent(resp)
    job = agent.generate(_ctx(), force=True)
    assert isinstance(job, BlogJob)


def test_generate_raises_on_invalid_json() -> None:
    agent = _make_agent({})
    agent._llm_client.models.generate_content.return_value.text = "not json"
    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(_ctx())


def test_generate_calls_model_with_topic_in_prompt() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    agent.generate(_ctx(topic="Rust concurrency"))
    call = agent._llm_client.models.generate_content.call_args
    contents = call[1].get("contents") or call[0][1]
    assert "Rust concurrency" in contents


# ------------------------------------------------------------------ #
# WriterAgent.generate_revision                                        #
# ------------------------------------------------------------------ #

def test_generate_revision_returns_blog_job() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = BlogJob(title="Old title", revise_instruction="Fix the intro.")
    result = agent.generate_revision(job, _ctx())
    assert isinstance(result, BlogJob)


def test_generate_revision_includes_revise_instruction_in_prompt() -> None:
    agent = _make_agent(_VALID_RESPONSE)
    job = BlogJob(title="Old title", revise_instruction="Add code examples please.")
    agent.generate_revision(job, _ctx())
    call = agent._llm_client.models.generate_content.call_args
    contents = call[1].get("contents") or call[0][1]
    assert "Add code examples" in contents


def test_generate_revision_uses_force_true() -> None:
    """generate_revision always uses force=True — multi-topic guard bypassed."""
    resp = {**_VALID_RESPONSE, "is_single_topic": False}
    agent = _make_agent(resp)
    job = BlogJob(title="Old title", revise_instruction="Fix it.")
    # Should NOT raise even though is_single_topic=False
    result = agent.generate_revision(job, _ctx())
    assert isinstance(result, BlogJob)
