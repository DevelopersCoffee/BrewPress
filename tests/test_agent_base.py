"""Tests for brewpress.agent_base — BaseAgent skill loading, tool dispatch, LLM access."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brewpress.agent_base import BaseAgent, _find_skill, _load_skill, _SKILL_CACHE
from brewpress.config import BrewPressConfig


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _cfg(api_key: str = "") -> BrewPressConfig:
    return BrewPressConfig(google_api_key=api_key or None)


def _make_agent(tmp_path: Path, extra_tools: list[str] | None = None) -> BaseAgent:
    """Build a concrete BaseAgent subclass with a real skill file."""
    skill = tmp_path / "test_skill.md"
    skill.write_text("You are a test agent.", encoding="utf-8")

    class _Agent(BaseAgent):
        SKILL = str(skill)
        TOOLS = extra_tools or []

    return _Agent(_cfg())


# ------------------------------------------------------------------ #
# _find_skill                                                          #
# ------------------------------------------------------------------ #

def test_find_skill_absolute_path_returned_when_exists(tmp_path: Path) -> None:
    skill = tmp_path / "my_skill.md"
    skill.write_text("x")
    result = _find_skill(str(skill))
    assert result == skill


def test_find_skill_raises_for_nonexistent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _find_skill(str(tmp_path / "does_not_exist.md"))


# ------------------------------------------------------------------ #
# system_prompt / skill loading                                        #
# ------------------------------------------------------------------ #

def test_system_prompt_returns_skill_file_content(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    assert agent.system_prompt == "You are a test agent."


def test_system_prompt_cached_after_first_read(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    _ = agent.system_prompt
    # Overwrite file — cached value should not change
    agent._skill_path.write_text("CHANGED", encoding="utf-8")
    assert agent.system_prompt == "You are a test agent."


def test_reload_skill_forces_fresh_read(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    _ = agent.system_prompt
    agent._skill_path.write_text("UPDATED CONTENT", encoding="utf-8")
    agent.reload_skill()
    assert agent.system_prompt == "UPDATED CONTENT"


# ------------------------------------------------------------------ #
# use() — tool dispatch                                                #
# ------------------------------------------------------------------ #

def test_use_raises_permission_error_for_unlisted_tool(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path, extra_tools=["allowed.tool"])
    with pytest.raises(PermissionError, match="not allowed"):
        agent.use("forbidden.tool")


def test_use_calls_registered_tool(tmp_path: Path) -> None:
    from brewpress import tools as _tools

    called_with: dict = {}

    def _fake(title: str) -> dict:
        called_with["title"] = title
        return {"ok": True}

    _tools._REGISTRY["test.qa_tool"] = _fake

    class _Agent(BaseAgent):
        SKILL = str(tmp_path / "s.md")
        TOOLS = ["test.qa_tool"]

    (tmp_path / "s.md").write_text("x")
    agent = _Agent(_cfg())

    result = agent.use("test.qa_tool", title="Hello")
    assert result == {"ok": True}
    assert called_with["title"] == "Hello"

    del _tools._REGISTRY["test.qa_tool"]


def test_use_raises_key_error_for_unregistered_tool(tmp_path: Path) -> None:
    class _Agent(BaseAgent):
        SKILL = str(tmp_path / "s.md")
        TOOLS = ["missing.tool"]

    (tmp_path / "s.md").write_text("x")
    agent = _Agent(_cfg())

    with pytest.raises(KeyError):
        agent.use("missing.tool")


# ------------------------------------------------------------------ #
# think() — LLM access                                                 #
# ------------------------------------------------------------------ #

def test_think_raises_without_api_key(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        agent.think("prompt")


def test_think_calls_llm_and_returns_text(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "LLM response text"
    mock_client.models.generate_content.return_value = mock_resp

    agent._llm_client = mock_client
    agent._llm_types = MagicMock()
    agent._config = _cfg(api_key="fake-key")

    result = agent.think("my prompt")
    assert result == "LLM response text"


def test_think_returns_empty_string_when_response_text_is_none(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = None
    mock_client.models.generate_content.return_value = mock_resp

    agent._llm_client = mock_client
    agent._llm_types = MagicMock()
    agent._config = _cfg(api_key="fake-key")

    result = agent.think("my prompt")
    assert result == ""


def test_think_passes_system_prompt_to_config(tmp_path: Path) -> None:
    skill = tmp_path / "skill.md"
    skill.write_text("System: be helpful.", encoding="utf-8")

    class _Agent(BaseAgent):
        SKILL = str(skill)
        TOOLS = []

    agent = _Agent(_cfg(api_key="fake"))

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "ok"
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client

    captured_kwargs: dict = {}
    original_types = MagicMock()

    def capture(**kw):
        captured_kwargs.update(kw)
        return MagicMock()

    original_types.GenerateContentConfig.side_effect = capture
    agent._llm_types = original_types

    agent.think("hello")
    assert captured_kwargs.get("system_instruction") == "System: be helpful."


def test_think_uses_response_schema_when_provided(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class _Schema(BaseModel):
        title: str

    agent = _make_agent(tmp_path)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "x"}'
    mock_client.models.generate_content.return_value = mock_resp
    agent._llm_client = mock_client

    captured: dict = {}
    mock_types = MagicMock()
    mock_types.GenerateContentConfig.side_effect = lambda **kw: (captured.update(kw), MagicMock())[1]
    agent._llm_types = mock_types

    agent.think("prompt", response_schema=_Schema)
    assert captured.get("response_schema") is _Schema


# ------------------------------------------------------------------ #
# LLM lazy initialization                                              #
# ------------------------------------------------------------------ #

def test_llm_client_not_initialized_at_construction(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    assert agent._llm_client is None


def test_llm_client_initialized_after_think_call(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    agent._config = _cfg(api_key="fake-key")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "response"
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        with patch("google.genai.types"):
            agent.think("hello")

    assert agent._llm_client is mock_client
