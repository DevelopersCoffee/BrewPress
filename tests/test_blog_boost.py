"""Tests for brewpress.blog_boost — Blog Boost Assistant."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brewpress.blog_boost import (
    _PROMPT_BUILDERS,
    BlogBoostAgent,
    BoostRequest,
    BoostResult,
    SEOSuggestions,
    _extract_json,
    _parse_boost_response,
)

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

_MINIMAL_RESPONSE: dict = {
    "optimized_content": "",
    "seo_suggestions": {
        "keywords_used": [],
        "missing_keywords": [],
        "title_feedback": "",
        "meta_description": "",
        "readability_score": "",
    },
    "structure_improvements": [],
    "engagement_tips": [],
}

_FULL_RESPONSE: dict = {
    "optimized_content": "# Kubernetes Basics\n\nIntro paragraph here.",
    "seo_suggestions": {
        "keywords_used": ["kubernetes basics", "container orchestration"],
        "missing_keywords": ["kubectl"],
        "title_feedback": "Good — primary keyword near the front.",
        "meta_description": "Learn Kubernetes basics: deploy and scale containers.",
        "readability_score": "Grade 10 — appropriate for senior developers.",
    },
    "structure_improvements": [
        "Add an H2 section for 'Prerequisites'.",
        "Move the code block to the top of the relevant section.",
    ],
    "engagement_tips": [
        "Add a 'Further Reading' section with internal links.",
        "Include a real-world architecture diagram.",
    ],
}


def _make_agent(response_dict: dict) -> BlogBoostAgent:
    """Create a BlogBoostAgent with a mocked Gemini client."""
    agent = object.__new__(BlogBoostAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    mock_client.models.generate_content.return_value = mock_resp
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()
    return agent


# ------------------------------------------------------------------ #
# BoostRequest construction                                            #
# ------------------------------------------------------------------ #


def test_boost_request_defaults() -> None:
    req = BoostRequest(task_type="seo_audit")
    assert req.content == ""
    assert req.keywords == []
    assert req.format == "blog"
    assert req.word_count is None


def test_boost_request_with_all_fields() -> None:
    req = BoostRequest(
        task_type="rewrite",
        content="Some content",
        keywords=["k8s", "docker"],
        target_audience="DevOps engineers",
        tone="technical and direct",
        word_count=800,
        format="blog",
    )
    assert req.task_type == "rewrite"
    assert req.word_count == 800
    assert "k8s" in req.keywords


def test_boost_request_rejects_invalid_task_type() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BoostRequest(task_type="unknown_task")  # type: ignore[arg-type]


def test_boost_request_rejects_word_count_below_minimum() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BoostRequest(task_type="rewrite", word_count=50)


# ------------------------------------------------------------------ #
# _extract_json                                                        #
# ------------------------------------------------------------------ #


def test_extract_json_bare_object() -> None:
    raw = '{"key": "value"}'
    assert _extract_json(raw) == '{"key": "value"}'


def test_extract_json_strips_markdown_fence() -> None:
    raw = "```json\n{\"key\": \"value\"}\n```"
    result = _extract_json(raw)
    assert result.startswith("{")


def test_extract_json_embedded_in_prose() -> None:
    raw = 'Here is the result: {"key": "value"} — done.'
    result = _extract_json(raw)
    assert result == '{"key": "value"}'


def test_extract_json_strips_bom() -> None:
    raw = '\ufeff{"key": "value"}'
    assert _extract_json(raw).startswith("{")


# ------------------------------------------------------------------ #
# _parse_boost_response                                                #
# ------------------------------------------------------------------ #


def test_parse_minimal_response() -> None:
    raw = json.dumps(_MINIMAL_RESPONSE)
    result = _parse_boost_response(raw, "seo_audit")
    assert isinstance(result, BoostResult)
    assert result.task_type == "seo_audit"
    assert result.optimized_content == ""
    assert result.structure_improvements == []


def test_parse_full_response() -> None:
    raw = json.dumps(_FULL_RESPONSE)
    result = _parse_boost_response(raw, "rewrite")
    assert result.optimized_content.startswith("# Kubernetes")
    assert "kubernetes basics" in result.seo_suggestions.keywords_used
    assert "kubectl" in result.seo_suggestions.missing_keywords
    assert len(result.structure_improvements) == 2
    assert len(result.engagement_tips) == 2


def test_parse_invalid_json_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_boost_response("not json at all", "seo_audit")


def test_parse_tolerates_null_seo_suggestions() -> None:
    raw = json.dumps({**_MINIMAL_RESPONSE, "seo_suggestions": None})
    result = _parse_boost_response(raw, "content_feedback")
    assert isinstance(result.seo_suggestions, SEOSuggestions)


# ------------------------------------------------------------------ #
# BoostResult                                                          #
# ------------------------------------------------------------------ #


def test_boost_result_to_json_excludes_raw() -> None:
    result = BoostResult(
        task_type="seo_audit",
        raw_model_output="<raw response>",
    )
    data = result.to_json()
    assert "raw_model_output" not in data
    assert "task_type" in data


def test_boost_result_to_json_round_trip() -> None:
    raw = json.dumps(_FULL_RESPONSE)
    result = _parse_boost_response(raw, "rewrite")
    data = result.to_json()
    assert data["task_type"] == "rewrite"
    assert data["seo_suggestions"]["keywords_used"] == [
        "kubernetes basics", "container orchestration"
    ]


# ------------------------------------------------------------------ #
# Prompt builders                                                      #
# ------------------------------------------------------------------ #


def test_all_task_types_have_prompt_builders() -> None:
    import typing

    from brewpress.blog_boost import TaskType

    task_types = set(typing.get_args(TaskType))
    assert task_types == set(_PROMPT_BUILDERS.keys())


def test_seo_audit_prompt_contains_keywords() -> None:
    req = BoostRequest(task_type="seo_audit", content="some text", keywords=["spring boot"])
    prompt = _PROMPT_BUILDERS["seo_audit"](req)
    assert "spring boot" in prompt


def test_rewrite_prompt_includes_word_count_when_set() -> None:
    req = BoostRequest(task_type="rewrite", content="some text", word_count=600)
    prompt = _PROMPT_BUILDERS["rewrite"](req)
    assert "600" in prompt


def test_rewrite_prompt_omits_word_count_when_none() -> None:
    req = BoostRequest(task_type="rewrite", content="some text")
    prompt = _PROMPT_BUILDERS["rewrite"](req)
    assert "Target word count" not in prompt


def test_meta_description_prompt_cites_character_rule() -> None:
    req = BoostRequest(task_type="meta_description", content="some text")
    prompt = _PROMPT_BUILDERS["meta_description"](req)
    assert "120" in prompt and "160" in prompt


def test_engagement_message_prompt_uses_format() -> None:
    req = BoostRequest(task_type="engagement_message", format="email")
    prompt = _PROMPT_BUILDERS["engagement_message"](req)
    assert "email" in prompt


def test_topic_ideas_prompt_includes_seed_keywords() -> None:
    req = BoostRequest(task_type="topic_ideas", keywords=["docker", "ci/cd"])
    prompt = _PROMPT_BUILDERS["topic_ideas"](req)
    assert "docker" in prompt


# ------------------------------------------------------------------ #
# BlogBoostAgent construction                                          #
# ------------------------------------------------------------------ #


def test_agent_raises_without_api_key() -> None:
    from brewpress.config import BrewPressConfig

    cfg = BrewPressConfig()  # no google_api_key
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        BlogBoostAgent(cfg)


# ------------------------------------------------------------------ #
# BlogBoostAgent.run                                                   #
# ------------------------------------------------------------------ #


def test_run_seo_audit_returns_boost_result() -> None:
    agent = _make_agent(_FULL_RESPONSE)
    req = BoostRequest(
        task_type="seo_audit",
        content="Intro to Kubernetes...",
        keywords=["kubernetes basics"],
    )
    result = agent.run(req)
    assert isinstance(result, BoostResult)
    assert result.task_type == "seo_audit"


def test_run_calls_model_with_content() -> None:
    agent = _make_agent(_MINIMAL_RESPONSE)
    req = BoostRequest(task_type="seo_audit", content="my post content")
    agent.run(req)
    call = agent._client.models.generate_content.call_args
    contents = call[1].get("contents") or call[0][1]
    assert "my post content" in contents


def test_run_rewrite_returns_optimized_content() -> None:
    resp = {**_MINIMAL_RESPONSE, "optimized_content": "# Rewritten Post\n\nBody."}
    agent = _make_agent(resp)
    req = BoostRequest(task_type="rewrite", content="old content")
    result = agent.run(req)
    assert result.optimized_content.startswith("# Rewritten Post")


def test_run_title_suggestions_returns_titles() -> None:
    resp = {
        **_MINIMAL_RESPONSE,
        "optimized_content": "1. Java 21 Virtual Threads Explained\n2. Inside JVM Virtual Threads",
        "seo_suggestions": {**_MINIMAL_RESPONSE["seo_suggestions"],
                             "title_feedback": "Strong primary keyword placement."},
    }
    agent = _make_agent(resp)
    req = BoostRequest(task_type="title_suggestions", content="post about Java 21")
    result = agent.run(req)
    assert "Virtual Threads" in result.optimized_content
    assert result.seo_suggestions.title_feedback != ""


def test_run_meta_description_populates_seo_field() -> None:
    resp = {
        **_MINIMAL_RESPONSE,
        "seo_suggestions": {
            **_MINIMAL_RESPONSE["seo_suggestions"],
            "meta_description": "Learn Kubernetes basics in 10 minutes.",
        },
    }
    agent = _make_agent(resp)
    req = BoostRequest(task_type="meta_description", content="k8s intro")
    result = agent.run(req)
    assert "Kubernetes" in result.seo_suggestions.meta_description


def test_run_content_feedback_returns_structure_improvements() -> None:
    resp = {
        **_MINIMAL_RESPONSE,
        "structure_improvements": ["Add prerequisites section.", "Move TL;DR to top."],
    }
    agent = _make_agent(resp)
    req = BoostRequest(task_type="content_feedback", content="draft post")
    result = agent.run(req)
    assert len(result.structure_improvements) == 2


def test_run_topic_ideas_returns_content() -> None:
    resp = {**_MINIMAL_RESPONSE, "optimized_content": "1. Java 21\n2. Spring Boot 3"}
    agent = _make_agent(resp)
    req = BoostRequest(task_type="topic_ideas", keywords=["java", "spring"])
    result = agent.run(req)
    assert "Java" in result.optimized_content


def test_run_engagement_message_returns_message() -> None:
    resp = {
        **_MINIMAL_RESPONSE,
        "optimized_content": "Hi! We'd love a contribution on Spring AI.",
        "engagement_tips": ["Follow up within a week."],
    }
    agent = _make_agent(resp)
    req = BoostRequest(task_type="engagement_message", format="email")
    result = agent.run(req)
    assert "contribution" in result.optimized_content
    assert len(result.engagement_tips) == 1


def test_run_raises_value_error_on_bad_json() -> None:
    agent = object.__new__(BlogBoostAgent)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "not json"
    mock_client.models.generate_content.return_value = mock_resp
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    req = BoostRequest(task_type="seo_audit", content="test")
    with pytest.raises(ValueError, match="invalid JSON"):
        agent.run(req)
