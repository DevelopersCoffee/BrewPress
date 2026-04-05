"""Tests for brewpress.cli — argument parsing and subcommand stubs."""

from __future__ import annotations

import pytest

from brewpress.cli import build_parser, main

# ------------------------------------------------------------------ #
# draft — argument validation                                          #
# ------------------------------------------------------------------ #


def test_draft_with_diff_only(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--diff", "my.diff"])
    assert args.diff_path == "my.diff"
    assert args.topic == ""


def test_draft_with_topic_only(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--topic", "Rate limiting in Go"])
    assert args.topic == "Rate limiting in Go"
    assert args.diff_path is None


def test_draft_with_both_diff_and_topic() -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--diff", "my.diff", "--topic", "Rate limiting"])
    assert args.diff_path == "my.diff"
    assert args.topic == "Rate limiting"


def test_draft_with_neither_raises(capsys: pytest.CaptureFixture[str]) -> None:
    """Neither --diff nor --topic should exit with a usage error."""
    with pytest.raises(SystemExit) as exc_info:
        main.__module__  # warm up import
        import sys
        sys.argv = ["brewpress", "draft"]
        from brewpress.cli import main as _main
        _main()
    assert exc_info.value.code != 0


def test_draft_auto_approve_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--diff", "x.diff", "--auto-approve"])
    assert args.auto_approve is True


def test_draft_force_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--diff", "x.diff", "--force"])
    assert args.force is True


def test_draft_files_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["draft", "--diff", "x.diff", "--files", "a.py", "b.py"])
    assert args.files == ["a.py", "b.py"]


# ------------------------------------------------------------------ #
# calibrate stub                                                       #
# ------------------------------------------------------------------ #


def test_calibrate_writes_tone_json(
    tmp_path: pytest.fixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """calibrate fetches WP posts and writes tone.json."""
    import sys
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from brewpress.config import BrewPressConfig

    mock_posts = [
        {
            "id": 1,
            "title": {"rendered": "Post One"},
            "slug": "post-one",
            "date": "2024-01-01",
            "excerpt": {"rendered": ""},
        }
    ]
    mock_client = MagicMock()
    mock_client._get.return_value = mock_posts

    mock_config = BrewPressConfig(
        wp_url="https://example.com",
        wp_username="admin",
        wp_app_password="pass",
    )

    sys.argv = ["brewpress", "calibrate"]
    from brewpress.cli import main as _main
    with (
        patch("brewpress.config.load_config", return_value=mock_config),
        patch("brewpress.wp_client.WordPressClient", return_value=mock_client),
        patch("pathlib.Path.home", return_value=Path(tmp_path)),
    ):
        rc = _main()

    assert rc == 0
    out = capsys.readouterr().out
    assert "tone" in out.lower() or "post" in out.lower()


def test_calibrate_force_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["calibrate", "--force"])
    assert args.force is True


# ------------------------------------------------------------------ #
# approve-publish --live flag                                          #
# ------------------------------------------------------------------ #


def test_approve_publish_live_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["approve-publish", "--live"])
    assert args.live is True


def test_approve_publish_default_not_live() -> None:
    parser = build_parser()
    args = parser.parse_args(["approve-publish"])
    assert args.live is False


# ------------------------------------------------------------------ #
# revise <instruction>                                                 #
# ------------------------------------------------------------------ #


def test_revise_parses_instruction() -> None:
    parser = build_parser()
    args = parser.parse_args(["revise", "shorten the introduction"])
    assert args.instruction == "shorten the introduction"


def test_revise_instruction_is_positional() -> None:
    """instruction is a positional arg — no flag prefix needed."""
    parser = build_parser()
    args = parser.parse_args(["revise", "fix the tone please"])
    assert args.command == "revise"
    assert "fix" in args.instruction


# ------------------------------------------------------------------ #
# reject --reason flag                                                 #
# ------------------------------------------------------------------ #


def test_reject_reason_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["reject", "--reason", "off brand"])
    assert args.reason == "off brand"


def test_reject_default_empty_reason() -> None:
    parser = build_parser()
    args = parser.parse_args(["reject"])
    assert args.reason == ""


# ------------------------------------------------------------------ #
# --version flag                                                       #
# ------------------------------------------------------------------ #


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    import sys
    sys.argv = ["brewpress", "--version"]
    from brewpress.cli import main as _main
    rc = _main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == "1.0.0"


# ------------------------------------------------------------------ #
# No subcommand prints help                                            #
# ------------------------------------------------------------------ #


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    import sys
    sys.argv = ["brewpress"]
    from brewpress.cli import main as _main
    rc = _main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "COMMAND" in out
