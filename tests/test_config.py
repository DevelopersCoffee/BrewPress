"""Tests for brewpress.config — env var loading and validation."""

from __future__ import annotations

import os
import pytest

from brewpress.config import BrewPressConfig, load_config

_VALID_ENV = {
    "WP_URL": "https://example.com",
    "WP_USERNAME": "admin",
    "WP_APP_PASSWORD": "abcd efgh ijkl mnop qrst uvwx",
    "GOOGLE_API_KEY": "test-api-key",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str] | None = None) -> None:
    env = {**_VALID_ENV, **(overrides or {})}
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_load_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = load_config()
    assert isinstance(cfg, BrewPressConfig)
    assert cfg.wp_url == "https://example.com"
    assert cfg.wp_username == "admin"
    assert cfg.google_api_key == "test-api-key"


def test_load_config_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {"WP_URL": "https://example.com/"})
    cfg = load_config()
    assert cfg.wp_url == "https://example.com"


def test_load_config_missing_var(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("WP_APP_PASSWORD")
    with pytest.raises(EnvironmentError, match="WP_APP_PASSWORD"):
        load_config()


def test_load_config_empty_var_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {"GOOGLE_API_KEY": "   "})
    with pytest.raises(EnvironmentError, match="GOOGLE_API_KEY"):
        load_config()


def test_load_config_multiple_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in _VALID_ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(EnvironmentError) as exc_info:
        load_config()
    msg = str(exc_info.value)
    assert "WP_URL" in msg
    assert "WP_USERNAME" in msg


def test_config_is_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = load_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.wp_url = "https://other.example.com"  # type: ignore[misc]
