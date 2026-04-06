"""BrewPress tool registry.

Tools are pure Python functions — no LLM calls, no I/O side-effects beyond
what their signature documents.  Agents call tools first; LLM is the last resort.

Registration:

    from brewpress.tools import register, call

    @register("seo_check_title")
    def check_title(title: str) -> dict:
        ...

    result = call("seo_check_title", title="My Post")

All registered tools are auto-imported when this package is first loaded.
"""

from __future__ import annotations

from typing import Any, Callable

# ------------------------------------------------------------------ #
# Registry                                                             #
# ------------------------------------------------------------------ #

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str) -> Callable:
    """Decorator: register a function as a named tool.

    Example:
        @register("seo_check_title")
        def _check(title: str) -> dict:
            ...
    """
    def _decorator(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"Tool {name!r} already registered.")
        _REGISTRY[name] = fn
        return fn
    return _decorator


def call(name: str, **kwargs: Any) -> Any:
    """Call a registered tool by name.

    Raises:
        KeyError:   Tool not found.
        TypeError:  Wrong arguments (propagated from the tool function).
    """
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown tool {name!r}. "
            f"Available: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[name](**kwargs)


def list_tools() -> list[str]:
    """Return sorted list of all registered tool names."""
    return sorted(_REGISTRY.keys())


# ------------------------------------------------------------------ #
# Auto-import all tool modules so decorators run                       #
# ------------------------------------------------------------------ #

from brewpress.tools import seo, content  # noqa: E402, F401
