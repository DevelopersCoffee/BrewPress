"""Tests for brewpress.config — env var loading and validation."""

from __future__ import annotations

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


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in _VALID_ENV:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent _load_dotenv from reading the real .env during tests."""
    monkeypatch.setattr("brewpress.config._load_dotenv", lambda: None)


# ------------------------------------------------------------------ #
# Existing tests (all 4 vars required — default behaviour)            #
# ------------------------------------------------------------------ #


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


# ------------------------------------------------------------------ #
# Per-subcommand loading — partial required sets                      #
# ------------------------------------------------------------------ #


def test_load_config_generation_only_no_wp_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """draft subcommand: only GOOGLE_API_KEY required; WP vars may be absent."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    cfg = load_config(required=("GOOGLE_API_KEY",))
    assert cfg.google_api_key == "test-key"
    assert cfg.wp_url is None
    assert cfg.wp_username is None
    assert cfg.wp_app_password is None


def test_load_config_generation_only_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with pytest.raises(EnvironmentError, match="GOOGLE_API_KEY"):
        load_config(required=("GOOGLE_API_KEY",))


def test_load_config_wp_only_no_google_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """calibrate/approve-publish: WP vars required; GOOGLE_API_KEY may be absent."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("WP_URL", "https://example.com")
    monkeypatch.setenv("WP_USERNAME", "admin")
    monkeypatch.setenv("WP_APP_PASSWORD", "xxxx yyyy zzzz")
    cfg = load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
    assert cfg.wp_url == "https://example.com"
    assert cfg.wp_username == "admin"
    assert cfg.google_api_key is None


def test_load_config_wp_only_missing_var(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("WP_URL", "https://example.com")
    monkeypatch.setenv("WP_USERNAME", "admin")
    # WP_APP_PASSWORD absent
    with pytest.raises(EnvironmentError, match="WP_APP_PASSWORD"):
        load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))


def test_load_config_empty_required_no_vars_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = load_config(required=())
    assert cfg.wp_url is None
    assert cfg.google_api_key is None


# ------------------------------------------------------------------ #
# HTTPS warning                                                        #
# ------------------------------------------------------------------ #


def test_https_warning_on_http_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_env(monkeypatch, {"WP_URL": "http://example.com"})
    load_config()
    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "HTTPS" in captured.err


def test_no_https_warning_on_https_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_env(monkeypatch)
    load_config()
    captured = capsys.readouterr()
    assert captured.err == ""


def test_no_https_warning_when_wp_url_not_required(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    load_config(required=("GOOGLE_API_KEY",))
    captured = capsys.readouterr()
    assert captured.err == ""
