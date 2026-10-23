"""Tests for centralized Gemini model configuration."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from brewpress.agent_base import BaseAgent
from brewpress.config import (
    DEFAULT_GEMINI_MODEL,
    RETIRED_GEMINI_MODEL_IDS,
    BrewPressConfig,
    gemini_model,
)

_GEMINI_ID_RE = re.compile(r"gemini-[a-z0-9][a-z0-9.-]*")
_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("brewpress.config._load_dotenv", lambda: None)


def test_default_gemini_model_not_retired() -> None:
    assert DEFAULT_GEMINI_MODEL not in RETIRED_GEMINI_MODEL_IDS


def test_no_retired_gemini_model_ids_in_src() -> None:
    """Production code must not reference shutdown Gemini model ids."""
    violations: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path.name == "config.py":
            continue
        for model_id in _GEMINI_ID_RE.findall(path.read_text(encoding="utf-8")):
            if model_id in RETIRED_GEMINI_MODEL_IDS:
                violations.append(f"{path.relative_to(_SRC_ROOT.parent)}: {model_id!r}")
    assert not violations, "Retired Gemini models in src:\n" + "\n".join(violations)


def test_brewpress_model_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREWPRESS_MODEL", raising=False)
    assert gemini_model() == DEFAULT_GEMINI_MODEL

    monkeypatch.setenv("BREWPRESS_MODEL", "gemini-3.1-pro-preview")
    assert gemini_model() == "gemini-3.1-pro-preview"


def test_base_agent_uses_brewpress_model_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = tmp_path / "skill.md"
    skill.write_text("test", encoding="utf-8")

    class _Agent(BaseAgent):
        SKILL = str(skill)

    monkeypatch.setenv("BREWPRESS_MODEL", "gemini-override-test")
    cfg = BrewPressConfig(google_api_key="key")
    agent = _Agent(cfg)
    assert agent._model == "gemini-override-test"
