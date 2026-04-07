"""Tests for brewpress.structurer_agent — StructurerAgent heading and structure enforcement."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brewpress.models import BlogJob
from brewpress.structurer_agent import StructurerAgent, _build_prompt, _extract_json


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

_BODY = (
    "# Java Virtual Threads\n\n"
    "Java 21 changed concurrency forever.\n\n"
    "## What are virtual threads?\n\n"
    "Lightweight JVM-managed threads.\n\n"
    "## When to use them\n\n"
    "I/O-bound workloads. Not CPU-bound.\n"
)


def _job(**kwargs) -> BlogJob:
    defaults = dict(
        title="Java 21 Virtual Threads",
        meta_description="A practical guide to Java virtual threads.",
        draft_body_md=_BODY,
    )
    defaults.update(kwargs)
    return BlogJob(**defaults)


def _make_agent(tool_result: dict, llm_response: str = "") -> StructurerAgent:
    agent = object.__new__(StructurerAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = llm_response
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client
    agent._llm_types = MagicMock()
    agent._model = "gemini-2.0-flash"
    agent._config = MagicMock()
    agent._skill_path = Path("skills/structurer.md")
    agent._skill_text = "You are a structurer."
    agent._tool_result = tool_result
    return agent


def _patch_use(agent: StructurerAgent, result: dict) -> None:
    agent.use = MagicMock(return_value=result)  # type: ignore[method-assign]


# ------------------------------------------------------------------ #
# _extract_json                                                        #
# ------------------------------------------------------------------ #

def test_extract_json_plain_object() -> None:
    assert _extract_json('{"draft_body_md": "x"}') == '{"draft_body_md": "x"}'


def test_extract_json_strips_fence() -> None:
    raw = '```json\n{"draft_body_md": "x"}\n```'
    result = _extract_json(raw)
    assert result.startswith("{")


# ------------------------------------------------------------------ #
# _build_prompt                                                        #
# ------------------------------------------------------------------ #

def test_build_prompt_includes_issues() -> None:
    issues = ["Missing H1", "H3 used before H2"]
    prompt = _build_prompt(_job(), issues)
    assert "Missing H1" in prompt
    assert "H3 used before H2" in prompt


def test_build_prompt_includes_title() -> None:
    job = _job(title="Unique Title XYZ")
    prompt = _build_prompt(job, ["issue"])
    assert "Unique Title XYZ" in prompt


def test_build_prompt_truncates_long_body() -> None:
    long_body = "x " * 5000
    job = _job(draft_body_md=long_body)
    prompt = _build_prompt(job, ["issue"])
    assert "truncated" in prompt


# ------------------------------------------------------------------ #
# StructurerAgent.structure — fast path                                #
# ------------------------------------------------------------------ #

def test_structure_returns_job_unchanged_when_no_issues() -> None:
    agent = _make_agent(tool_result={})
    _patch_use(agent, {"issues": []})
    job = _job()
    result = agent.structure(job)
    assert result is job
    agent._llm_client.models.generate_content.assert_not_called()


def test_structure_fast_path_on_none_issues() -> None:
    agent = _make_agent(tool_result={})
    _patch_use(agent, {"issues": None})
    job = _job()
    result = agent.structure(job)
    assert result is job


# ------------------------------------------------------------------ #
# StructurerAgent.structure — LLM path                                 #
# ------------------------------------------------------------------ #

def test_structure_calls_llm_when_issues_found() -> None:
    new_body = "# Fixed\n\nRestructured content."
    llm_response = json.dumps({"draft_body_md": new_body})
    agent = _make_agent(tool_result={}, llm_response=llm_response)
    _patch_use(agent, {"issues": ["Missing H1 tag"]})
    job = _job()
    result = agent.structure(job)
    agent._llm_client.models.generate_content.assert_called_once()
    assert result.draft_body_md == new_body


def test_structure_returns_new_job_with_restructured_body() -> None:
    new_body = "# Restructured Title\n\nNew content here."
    llm_response = json.dumps({"draft_body_md": new_body})
    agent = _make_agent(tool_result={}, llm_response=llm_response)
    _patch_use(agent, {"issues": ["H2 before H1"]})
    job = _job()
    result = agent.structure(job)
    assert result.draft_body_md == new_body
    assert result is not job  # new object via model_copy


def test_structure_preserves_other_fields_when_restructuring() -> None:
    new_body = "# Fixed Body\n\nContent."
    llm_response = json.dumps({"draft_body_md": new_body})
    agent = _make_agent(tool_result={}, llm_response=llm_response)
    _patch_use(agent, {"issues": ["issue"]})
    job = _job(title="Keep This Title", primary_keyword="java 21 virtual threads")
    result = agent.structure(job)
    assert result.title == "Keep This Title"
    assert result.primary_keyword == "java 21 virtual threads"


def test_structure_returns_original_job_when_llm_returns_empty_body() -> None:
    llm_response = json.dumps({"draft_body_md": ""})
    agent = _make_agent(tool_result={}, llm_response=llm_response)
    _patch_use(agent, {"issues": ["issue"]})
    job = _job()
    result = agent.structure(job)
    assert result is job  # empty body guard — keep original


def test_structure_raises_on_invalid_json() -> None:
    agent = _make_agent(tool_result={}, llm_response="not json at all")
    _patch_use(agent, {"issues": ["issue"]})
    with pytest.raises(ValueError, match="invalid JSON"):
        agent.structure(_job())


def test_structure_passes_body_to_tool() -> None:
    new_body = "# Fixed\n\nContent.\n"
    llm_response = json.dumps({"draft_body_md": new_body})
    agent = _make_agent(tool_result={}, llm_response=llm_response)
    _patch_use(agent, {"issues": ["issue"]})
    job = _job(draft_body_md="# Original Body\n\nContent.\n")
    agent.structure(job)
    call_kwargs = agent.use.call_args[1]  # type: ignore[union-attr]
    assert "# Original Body" in call_kwargs.get("body", "")
