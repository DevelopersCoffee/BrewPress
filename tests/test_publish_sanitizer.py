"""Tests for publish_sanitizer.sanitize_body_for_publish."""

from __future__ import annotations

from brewpress.publish_sanitizer import sanitize_body_for_publish


def test_strips_executed_tutorial_steps_section() -> None:
    body = (
        "# Title\n\n"
        "Intro paragraph.\n\n"
        "## Executed Tutorial Steps\n\n"
        "```json\n[{\"step_id\": \"01\"}]\n```\n\n"
        "## Step 1: Setup\n\n"
        "Body of step one.\n"
    )
    out = sanitize_body_for_publish(body)
    assert "Executed Tutorial Steps" not in out
    assert "step_id" not in out
    assert "## Step 1: Setup" in out
    assert "Body of step one." in out
    assert "Intro paragraph." in out


def test_strips_execution_proof_section() -> None:
    body = (
        "## Step 1\n\nfoo\n\n"
        "## Execution Proof\n\nexit 0\nexit 0\n\n"
        "## Step 2\n\nbar\n"
    )
    out = sanitize_body_for_publish(body)
    assert "Execution Proof" not in out
    assert "exit 0" not in out
    assert "## Step 1" in out and "## Step 2" in out


def test_strips_screenshot_plan_section_at_eof() -> None:
    body = (
        "## Step 1\n\nfoo\n\n"
        "## Screenshot Plan for the Blog Pipeline\n\n"
        "- thing 1\n- thing 2\n"
    )
    out = sanitize_body_for_publish(body)
    assert "Screenshot Plan" not in out
    assert "thing 1" not in out
    assert "## Step 1" in out


def test_clean_body_unchanged() -> None:
    body = "# Title\n\n## Step 1\n\nbody\n\n## Step 2\n\nmore\n"
    assert sanitize_body_for_publish(body) == body


def test_idempotent() -> None:
    body = (
        "# Title\n\n"
        "## Executed Tutorial Steps\n\n```json\n[]\n```\n\n"
        "## Real Section\n\nkeep me\n"
    )
    once = sanitize_body_for_publish(body)
    twice = sanitize_body_for_publish(once)
    assert once == twice


def test_does_not_strip_h3_or_inline_text() -> None:
    body = (
        "## Real Section\n\n"
        "Mentions step_id inline but not as H2.\n\n"
        "### Executed Tutorial Steps\n\n"
        "This is an H3 with a colliding name; should be kept.\n"
    )
    out = sanitize_body_for_publish(body)
    assert "step_id" in out
    assert "### Executed Tutorial Steps" in out


def test_empty_body() -> None:
    assert sanitize_body_for_publish("") == ""


def test_no_h2_headings() -> None:
    body = "# Title\n\nJust a paragraph, no H2.\n"
    assert sanitize_body_for_publish(body) == body


def test_strips_all_three_section_types_together() -> None:
    body = (
        "# Title\n\nIntro.\n\n"
        "## Executed Tutorial Steps\n\n```json\n[]\n```\n\n"
        "## Execution Proof\n\nexit 0\n\n"
        "## Step 1\n\nreal content\n\n"
        "## Screenshot Plan for the Blog Pipeline\n\n- shot a\n"
    )
    out = sanitize_body_for_publish(body)
    assert "Executed Tutorial" not in out
    assert "Execution Proof" not in out
    assert "Screenshot Plan" not in out
    assert "real content" in out
    assert "## Step 1" in out


def test_h1_heading_terminates_stripped_section() -> None:
    """Regression: H1 between scaffolding and next H2 must NOT be deleted."""
    body = (
        "## Executed Tutorial Steps\n\n```json\n[]\n```\n\n"
        "# Standalone H1 Section\n\n"
        "Important content under H1 — must survive.\n\n"
        "## Step 1\n\nbody\n"
    )
    out = sanitize_body_for_publish(body)
    assert "Executed Tutorial Steps" not in out
    assert "step_id" not in out
    assert "# Standalone H1 Section" in out
    assert "Important content under H1 — must survive." in out
    assert "## Step 1" in out


def test_h1_scaffolding_title_not_stripped() -> None:
    """H1 with a scaffolding title is NOT stripped — only H2 is eligible."""
    body = (
        "# Executed Tutorial Steps\n\n"
        "This is an H1, not pipeline scaffolding.\n\n"
        "## Real Section\n\nbody\n"
    )
    out = sanitize_body_for_publish(body)
    assert "# Executed Tutorial Steps" in out
    assert "This is an H1" in out


def test_case_insensitive_match() -> None:
    body = (
        "## EXECUTED TUTORIAL STEPS\n\nfoo\n\n"
        "## Step 1\n\nbar\n"
    )
    out = sanitize_body_for_publish(body)
    assert "EXECUTED TUTORIAL" not in out
    assert "## Step 1" in out
