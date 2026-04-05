"""Tests for brewpress.draft_agent — prompt construction, response parsing,
BlogJob assembly, and DraftAgent behaviour (no live API calls)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brewpress.draft_agent import (
    _SECONDARY_KEYWORD_COUNT,
    _STYLE_GUIDE,
    DraftSchema,
    build_prompt,
    draft_to_job,
    parse_draft_response,
)
from brewpress.models import BlogJob, JobState
from brewpress.work_ingestion import WorkContext, ingest

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _ctx(
    topic: str = "Java 21 virtual threads",
    notes: str = "",
    is_code_post: bool = False,
) -> WorkContext:
    return ingest(topic=topic, notes=notes)


def _valid_draft_dict(**overrides: object) -> dict:
    base = {
        "title": "Java 21 Virtual Threads: A Practical Guide",
        "slug": "java-21-virtual-threads-practical-guide",
        "meta_description": (
            "Learn how Java 21 virtual threads simplify concurrent programming. "
            "Practical examples, benchmarks, and migration tips for backend developers."
        ),
        "excerpt": "Virtual threads arrived in Java 21. Here is what changes for you.",
        "primary_keyword": "Java 21 virtual threads",
        "secondary_keywords": ["project loom", "java concurrency", "jdk 21"],
        "outline": ["What are virtual threads", "Migration guide", "Benchmarks"],
        "draft_body_md": "## What are virtual threads\n\nVirtual threads are lightweight.",
        "is_single_topic": True,
        "tags": ["java", "concurrency", "jdk21", "backend"],
        "categories": ["Java", "Backend"],
        "quality_score": 85,
        "quality_gaps": ["missing benchmark numbers"],
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ #
# build_prompt — topic inclusion                                       #
# ------------------------------------------------------------------ #


def test_build_prompt_contains_topic() -> None:
    ctx = _ctx(topic="Spring Boot caching")
    assert "Spring Boot caching" in build_prompt(ctx)


def test_build_prompt_marks_idea_post() -> None:
    ctx = _ctx(is_code_post=False)
    assert "IDEA POST" in build_prompt(ctx)


def test_build_prompt_marks_code_post() -> None:
    ctx = ingest(topic="CI pipeline", notes="$ ./gradlew test")
    assert "CODE POST" in build_prompt(ctx)


def test_build_prompt_includes_notes() -> None:
    ctx = _ctx(notes="Focus on thread pools and platform threads comparison")
    assert "thread pools" in build_prompt(ctx)


def test_build_prompt_omits_notes_section_when_empty() -> None:
    ctx = _ctx(notes="")
    prompt = build_prompt(ctx)
    assert "**Notes:**" not in prompt


def test_build_prompt_includes_commands() -> None:
    ctx = ingest(topic="maven build", notes="$ mvn clean install")
    assert "mvn clean install" in build_prompt(ctx)


def test_build_prompt_omits_commands_section_when_none() -> None:
    ctx = _ctx()
    assert "Runnable commands" not in build_prompt(ctx)


def test_build_prompt_includes_diff_when_present(tmp_path: pytest.TempPathFactory) -> None:
    diff_text = (
        "diff --git a/Foo.java b/Foo.java\n"
        "--- a/Foo.java\n+++ b/Foo.java\n"
        "@@ -1,1 +1,2 @@\n-old\n+new\n"
    )
    diff_file = tmp_path / "changes.diff"
    diff_file.write_text(diff_text, encoding="utf-8")
    ctx = ingest(topic="Refactor Foo", diff_path=str(diff_file))
    assert "Foo.java" in build_prompt(ctx)
    assert "```diff" in build_prompt(ctx)


def test_build_prompt_omits_diff_when_absent() -> None:
    ctx = _ctx()
    assert "```diff" not in build_prompt(ctx)


def test_build_prompt_includes_pr_url() -> None:
    ctx = ingest(topic="foo", pr_url="https://github.com/org/repo/pull/7")
    assert "github.com/org/repo/pull/7" in build_prompt(ctx)


def test_build_prompt_omits_pr_url_when_absent() -> None:
    ctx = _ctx()
    assert "PR URL" not in build_prompt(ctx)


def test_build_prompt_requires_exact_keyword_count() -> None:
    ctx = _ctx()
    assert str(_SECONDARY_KEYWORD_COUNT) in build_prompt(ctx)


def test_build_prompt_references_grounding_constraint() -> None:
    ctx = _ctx()
    assert "invented" in build_prompt(ctx).lower()


# ------------------------------------------------------------------ #
# parse_draft_response — valid JSON                                    #
# ------------------------------------------------------------------ #


def test_parse_valid_json_returns_draft_schema() -> None:
    raw = json.dumps(_valid_draft_dict())
    schema = parse_draft_response(raw)
    assert isinstance(schema, DraftSchema)


def test_parse_extracts_title() -> None:
    raw = json.dumps(_valid_draft_dict(title="My Post"))
    assert parse_draft_response(raw).title == "My Post"


def test_parse_extracts_slug() -> None:
    raw = json.dumps(_valid_draft_dict(slug="my-post"))
    assert parse_draft_response(raw).slug == "my-post"


def test_parse_extracts_primary_keyword() -> None:
    raw = json.dumps(_valid_draft_dict(primary_keyword="spring boot"))
    assert parse_draft_response(raw).primary_keyword == "spring boot"


def test_parse_extracts_secondary_keywords() -> None:
    raw = json.dumps(_valid_draft_dict(secondary_keywords=["a", "b", "c"]))
    assert parse_draft_response(raw).secondary_keywords == ["a", "b", "c"]


def test_parse_extracts_quality_score() -> None:
    raw = json.dumps(_valid_draft_dict(quality_score=72))
    assert parse_draft_response(raw).quality_score == 72


def test_parse_extracts_is_single_topic_true() -> None:
    raw = json.dumps(_valid_draft_dict(is_single_topic=True))
    assert parse_draft_response(raw).is_single_topic is True


def test_parse_extracts_is_single_topic_false() -> None:
    raw = json.dumps(_valid_draft_dict(is_single_topic=False))
    assert parse_draft_response(raw).is_single_topic is False


# ------------------------------------------------------------------ #
# parse_draft_response — markdown fence stripping                     #
# ------------------------------------------------------------------ #


def test_parse_strips_json_fence() -> None:
    inner = json.dumps(_valid_draft_dict())
    raw = f"```json\n{inner}\n```"
    schema = parse_draft_response(raw)
    assert schema.title == _valid_draft_dict()["title"]


def test_parse_strips_plain_fence() -> None:
    inner = json.dumps(_valid_draft_dict())
    raw = f"```\n{inner}\n```"
    schema = parse_draft_response(raw)
    assert schema.slug == _valid_draft_dict()["slug"]


def test_parse_json_with_inner_code_fences() -> None:
    """Regression: JSON body containing fenced code blocks (e.g. ```java)
    must not confuse the fence-stripping logic and cause an empty extraction."""
    body_with_code = (
        "## Introduction\n\n"
        "Java is a language.\n\n"
        "```java\n"
        "public class Hello {\n"
        "    public static void main(String[] args) {\n"
        '        System.out.println("Hello");\n'
        "    }\n"
        "}\n"
        "```\n\n"
        "That is it."
    )
    d = _valid_draft_dict(draft_body_md=body_with_code)
    # Simulate the model wrapping the full JSON in a ```json fence — the
    # inner ```java block used to cause the non-greedy regex to terminate
    # early, returning an empty string and raising ValueError at char 0.
    raw = f"```json\n{json.dumps(d)}\n```"
    schema = parse_draft_response(raw)
    assert schema.title == d["title"]
    assert "```java" in schema.draft_body_md


def test_parse_bare_json_with_inner_code_fences() -> None:
    """Same regression but with bare JSON (no outer fence) — _extract_json
    fast-path must return the full object when the body has code blocks."""
    body_with_code = "## Intro\n\n```python\nprint('hi')\n```\n"
    d = _valid_draft_dict(draft_body_md=body_with_code)
    schema = parse_draft_response(json.dumps(d))
    assert "```python" in schema.draft_body_md


# ------------------------------------------------------------------ #
# parse_draft_response — clamping and error handling                  #
# ------------------------------------------------------------------ #


def test_parse_clamps_excess_secondary_keywords() -> None:
    too_many = ["a", "b", "c", "d", "e"]
    raw = json.dumps(_valid_draft_dict(secondary_keywords=too_many))
    schema = parse_draft_response(raw)
    assert len(schema.secondary_keywords) == _SECONDARY_KEYWORD_COUNT


def test_parse_invalid_json_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_draft_response("not json at all {{{")


def test_parse_missing_required_field_raises_value_error() -> None:
    d = _valid_draft_dict()
    del d["title"]
    with pytest.raises(ValueError, match="schema validation"):
        parse_draft_response(json.dumps(d))


def test_parse_quality_score_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="schema validation"):
        parse_draft_response(json.dumps(_valid_draft_dict(quality_score=150)))


# ------------------------------------------------------------------ #
# draft_to_job — BlogJob construction                                  #
# ------------------------------------------------------------------ #


def test_draft_to_job_returns_blog_job() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict())
    assert isinstance(draft_to_job(schema), BlogJob)


def test_draft_to_job_state_is_draft() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict())
    assert draft_to_job(schema).state == JobState.DRAFT


def test_draft_to_job_title_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(title="Custom Title"))
    assert draft_to_job(schema).title == "Custom Title"


def test_draft_to_job_slug_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(slug="custom-slug"))
    assert draft_to_job(schema).slug == "custom-slug"


def test_draft_to_job_meta_description_preserved() -> None:
    d = _valid_draft_dict()
    schema = DraftSchema.model_validate(d)
    assert draft_to_job(schema).meta_description == d["meta_description"]


def test_draft_to_job_primary_keyword_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(primary_keyword="loom"))
    assert draft_to_job(schema).primary_keyword == "loom"


def test_draft_to_job_secondary_keywords_preserved() -> None:
    kws = ["a", "b", "c"]
    schema = DraftSchema.model_validate(_valid_draft_dict(secondary_keywords=kws))
    assert draft_to_job(schema).secondary_keywords == kws


def test_draft_to_job_outline_preserved() -> None:
    outline = ["Intro", "Body", "Conclusion"]
    schema = DraftSchema.model_validate(_valid_draft_dict(outline=outline))
    assert draft_to_job(schema).outline == outline


def test_draft_to_job_body_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(draft_body_md="## Hello\n\nWorld"))
    assert draft_to_job(schema).draft_body_md == "## Hello\n\nWorld"


def test_draft_to_job_is_single_topic_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(is_single_topic=False))
    assert draft_to_job(schema).is_single_topic is False


def test_draft_to_job_quality_score_preserved() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict(quality_score=91))
    assert draft_to_job(schema).quality_score == 91


def test_draft_to_job_quality_gaps_preserved() -> None:
    gaps = ["needs benchmark", "thin intro"]
    schema = DraftSchema.model_validate(_valid_draft_dict(quality_gaps=gaps))
    assert draft_to_job(schema).quality_gaps == gaps


def test_draft_to_job_is_frozen() -> None:
    schema = DraftSchema.model_validate(_valid_draft_dict())
    job = draft_to_job(schema)
    with pytest.raises(Exception):
        job.title = "mutate"  # type: ignore[misc]


# ------------------------------------------------------------------ #
# DraftAgent — constructor guards                                      #
# ------------------------------------------------------------------ #


def test_draft_agent_raises_without_api_key() -> None:
    from brewpress.config import BrewPressConfig
    from brewpress.draft_agent import DraftAgent

    config = BrewPressConfig(google_api_key=None)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        DraftAgent(config)


# ------------------------------------------------------------------ #
# DraftAgent.generate — mocked client                                  #
# ------------------------------------------------------------------ #


def _stub_response(draft_dict: dict) -> MagicMock:
    resp = MagicMock()
    resp.text = json.dumps(draft_dict)
    return resp


def test_generate_returns_blog_job() -> None:
    from brewpress.draft_agent import DraftAgent

    agent = object.__new__(DraftAgent)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _stub_response(_valid_draft_dict())
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    ctx = _ctx()
    job = agent.generate(ctx)
    assert isinstance(job, BlogJob)
    assert job.state == JobState.DRAFT


def test_generate_calls_model_with_prompt() -> None:
    from brewpress.draft_agent import DraftAgent

    agent = object.__new__(DraftAgent)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _stub_response(_valid_draft_dict())
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    ctx = _ctx(topic="Spring Boot 3 caching")
    agent.generate(ctx)

    call_kwargs = mock_client.models.generate_content.call_args
    assert call_kwargs is not None
    # contents argument should contain the topic
    contents_arg = call_kwargs[1].get("contents") or call_kwargs[0][1]
    assert "Spring Boot 3 caching" in contents_arg


def test_generate_force_bypasses_single_topic_guard() -> None:
    from brewpress.draft_agent import DraftAgent

    agent = object.__new__(DraftAgent)
    mock_client = MagicMock()
    multi_topic = _valid_draft_dict(is_single_topic=False)
    mock_client.models.generate_content.return_value = _stub_response(multi_topic)
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    ctx = _ctx()
    job = agent.generate(ctx, force=True)
    assert job.is_single_topic is False


def test_generate_raises_without_force_on_multi_topic() -> None:
    from brewpress.draft_agent import DraftAgent

    agent = object.__new__(DraftAgent)
    mock_client = MagicMock()
    multi_topic = _valid_draft_dict(is_single_topic=False)
    mock_client.models.generate_content.return_value = _stub_response(multi_topic)
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    ctx = _ctx()
    with pytest.raises(ValueError, match="multiple topics"):
        agent.generate(ctx)


def test_generate_propagates_parse_error() -> None:
    from brewpress.draft_agent import DraftAgent

    agent = object.__new__(DraftAgent)
    mock_client = MagicMock()
    bad_resp = MagicMock()
    bad_resp.text = "not json {{{"
    mock_client.models.generate_content.return_value = bad_resp
    agent._client = mock_client
    agent._model = "gemini-2.0-flash"
    agent._types = MagicMock()

    with pytest.raises(ValueError, match="invalid JSON"):
        agent.generate(_ctx())


# ------------------------------------------------------------------ #
# Style guide sanity                                                   #
# ------------------------------------------------------------------ #


def test_style_guide_mentions_short_paragraphs() -> None:
    assert "paragraph" in _STYLE_GUIDE.lower()


def test_style_guide_mentions_no_fluff() -> None:
    assert "fluff" in _STYLE_GUIDE.lower()


def test_style_guide_mentions_no_invented_facts() -> None:
    assert "invented" in _STYLE_GUIDE.lower() or "invent" in _STYLE_GUIDE.lower()
