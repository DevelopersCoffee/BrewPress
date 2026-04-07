"""BaseAgent — minimal, skill-driven agent coordinator.

Design principles:
  1. Agents are thin.  All business logic lives in tools or skill files.
  2. Tools run first.  LLM is called only when tools cannot do the job.
  3. Skill files are Markdown.  Prompts, rules, and decision logic live in
     skills/*.md — editable without touching Python.
  4. The agent does not know which tools exist at import time.  Tools are
     registered separately (brewpress.tools) and injected at construction.

Usage:

    class MyCriticAgent(BaseAgent):
        SKILL = "skills/critic.md"
        TOOLS = ["seo.full", "content.structure_summary"]

        def review(self, job: BlogJob) -> CriticResult:
            # 1. Run tools deterministically
            seo = self.use("seo.full", title=job.title, ...)
            structure = self.use("content.structure_summary", body=job.draft_body_md)

            # 2. Only call LLM if tools flagged issues or for qualitative judgement
            if not seo["passed"] or not structure["passed"]:
                raw = self.think(build_prompt(job, seo, structure))
                return parse_response(raw)

            return default_pass_result()

The system_prompt property returns the contents of the skill file.
The think() method is the only way to call the LLM — explicitly named to
make LLM usage visible in code review.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from brewpress.config import BrewPressConfig


def _is_retryable_llm_error(exc: BaseException) -> bool:
    """Return True for transient Gemini API errors (429 rate-limit, 5xx server)."""
    msg = str(exc)
    return "429" in msg or any(msg.startswith(code) for code in ("500", "502", "503"))

# ------------------------------------------------------------------ #
# Skill loader                                                         #
# ------------------------------------------------------------------ #

_SKILL_CACHE: dict[str, str] = {}


def _load_skill(path: str | Path) -> str:
    """Load a skill Markdown file, cache after first read.

    Caching means hot-reloading isn't supported — restart the process
    to pick up skill file changes.  That's intentional: production agents
    shouldn't silently change behaviour mid-run.
    """
    key = str(Path(path).resolve())
    if key not in _SKILL_CACHE:
        _SKILL_CACHE[key] = Path(path).read_text(encoding="utf-8")
    return _SKILL_CACHE[key]


def _find_skill(relative: str | Path) -> Path:
    """Resolve a skill path relative to the project root or absolute."""
    p = Path(relative)
    if p.is_absolute() and p.exists():
        return p
    # Try relative to the project root (two levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent
    candidate = project_root / relative
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"Skill file not found: {relative!r}. "
        f"Tried: {candidate}"
    )


# ------------------------------------------------------------------ #
# BaseAgent                                                            #
# ------------------------------------------------------------------ #

_DEFAULT_MODEL = os.environ.get("BREWPRESS_MODEL", "gemini-2.0-flash")


class BaseAgent:
    """Thin skill-driven agent.

    Subclasses declare:
        SKILL: str | Path   — relative path to skills/*.md
        TOOLS: list[str]    — tool names this agent is allowed to use

    The skill file content becomes the LLM system prompt verbatim.
    Update skill files to change agent behaviour without touching Python.

    Args:
        config:     BrewPressConfig — must have google_api_key for think().
        skill_path: Override SKILL class attribute (useful in tests).
        model:      Gemini model name.
    """

    SKILL: str | Path = ""
    TOOLS: list[str] = []

    def __init__(
        self,
        config: BrewPressConfig,
        skill_path: str | Path | None = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._config = config
        self._model = model
        self._skill_path = _find_skill(skill_path or self.SKILL)
        self._skill_text: str | None = None   # lazy
        self._llm_client: Any = None           # lazy — only init if think() is called
        self._llm_types: Any = None

    # ---------------------------------------------------------------- #
    # Skill access                                                       #
    # ---------------------------------------------------------------- #

    @property
    def system_prompt(self) -> str:
        """Contents of the skill Markdown file."""
        if self._skill_text is None:
            self._skill_text = _load_skill(self._skill_path)
        return self._skill_text

    def reload_skill(self) -> None:
        """Force reload the skill file from disk (development only)."""
        key = str(self._skill_path.resolve())
        _SKILL_CACHE.pop(key, None)
        self._skill_text = None

    # ---------------------------------------------------------------- #
    # Tool dispatch                                                      #
    # ---------------------------------------------------------------- #

    def use(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool by name.

        Only tools listed in TOOLS can be called.  This constraint makes
        an agent's capabilities explicit and auditable from the class definition.

        Args:
            tool_name: Registered tool name (e.g. "seo.full").
            **kwargs:  Arguments forwarded to the tool function.

        Raises:
            PermissionError: Tool not in this agent's TOOLS list.
            KeyError:        Tool not registered at all.
        """
        if self.TOOLS and tool_name not in self.TOOLS:
            raise PermissionError(
                f"Agent {type(self).__name__} is not allowed to use tool {tool_name!r}. "
                f"Allowed: {self.TOOLS}"
            )
        from brewpress.tools import call
        return call(tool_name, **kwargs)

    # ---------------------------------------------------------------- #
    # LLM access — intentionally named "think" to make usage visible    #
    # ---------------------------------------------------------------- #

    def think(
        self,
        prompt: str,
        response_mime_type: str = "application/json",
        response_schema: Any = None,
        temperature: float = 0.3,
        max_output_tokens: int = 4096,
    ) -> str:
        """Call the LLM with the skill file as the system prompt.

        This is the ONLY way to call the LLM from an agent.  The explicit
        name makes LLM usage visible during code review — grep for ".think("
        to find every LLM call in the codebase.

        The system prompt is always the skill file contents.  Agents cannot
        override it inline — update the skill file instead.

        Args:
            prompt:              User-turn prompt.
            response_mime_type:  MIME type for the response.
            response_schema:     Pydantic model for structured output.
            temperature:         Sampling temperature.
            max_output_tokens:   Max tokens in response.

        Returns:
            Raw model response text.

        Raises:
            ValueError:  GOOGLE_API_KEY not set.
        """
        self._ensure_llm()
        kwargs: dict[str, Any] = {
            "system_instruction": self.system_prompt,
            "response_mime_type": response_mime_type,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if response_schema is not None:
            kwargs["response_schema"] = response_schema

        config = self._llm_types.GenerateContentConfig(**kwargs)
        response = self._call_llm(self._model, prompt, config)
        return response.text or ""

    @retry(
        retry=retry_if_exception(_is_retryable_llm_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30),
        reraise=True,
    )
    def _call_llm(self, model: str, contents: str, config: Any) -> Any:
        """Single LLM call with tenacity retry on 429/5xx."""
        return self._llm_client.models.generate_content(
            model=model, contents=contents, config=config
        )

    def _ensure_llm(self) -> None:
        if self._llm_client is not None:
            return
        if not self._config.google_api_key:
            raise ValueError(
                f"{type(self).__name__} needs GOOGLE_API_KEY to call think(). "
                "Set the environment variable or use tools-only mode."
            )
        from google import genai
        from google.genai import types as _types

        self._llm_client = genai.Client(api_key=self._config.google_api_key)
        self._llm_types = _types
