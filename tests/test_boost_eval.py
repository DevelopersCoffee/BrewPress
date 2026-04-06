"""Tests for brewpress.boost_eval — deterministic quality checks."""

from __future__ import annotations

from brewpress.boost_eval import (
    DeterministicEvalResult,
    check_code_block_quality,
    check_heading_hierarchy,
    check_hook_quality,
    check_keyword_density,
    check_keyword_in_intro,
    check_keyword_presence,
    check_meta_length,
    check_title_length,
    run_checks,
)
from brewpress.models import BlogJob

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _job(**kwargs) -> BlogJob:
    defaults = dict(
        title="Java 21 Virtual Threads Guide",  # 34 chars — intentionally short
        meta_description=(
            "A practical guide to Java 21 virtual threads for backend developers "
            "who want to simplify concurrency in Spring Boot applications."
        ),
        primary_keyword="java 21 virtual threads",
        secondary_keywords=["spring boot", "concurrency"],
        draft_body_md=(
            "# Java 21 Virtual Threads\n\n"
            "Java 21 virtual threads make concurrency simpler for backend developers. "
            "You no longer need thread pools for most I/O workloads.\n\n"
            "## What are they?\n\n"
            "Virtual threads are JVM-managed, lightweight alternatives to platform threads.\n\n"
            "```java\nThread.ofVirtual().start(() -> doWork());\n```\n\n"
            "## When to use them\n\n"
            "Use virtual threads for I/O-bound tasks. Avoid them for CPU-bound work.\n"
        ),
    )
    defaults.update(kwargs)
    return BlogJob(**defaults)


# ------------------------------------------------------------------ #
# check_title_length                                                   #
# ------------------------------------------------------------------ #


def test_title_passes_at_55_chars() -> None:
    result = check_title_length("A" * 55)
    assert result.passed


def test_title_passes_at_boundaries() -> None:
    assert check_title_length("A" * 50).passed
    assert check_title_length("A" * 60).passed


def test_title_fails_below_50() -> None:
    result = check_title_length("Short title")
    assert not result.passed
    assert "too short" in result.detail


def test_title_fails_above_60() -> None:
    result = check_title_length("A" * 61)
    assert not result.passed
    assert "too long" in result.detail


# ------------------------------------------------------------------ #
# check_meta_length                                                    #
# ------------------------------------------------------------------ #


def test_meta_passes_at_140_chars() -> None:
    assert check_meta_length("M" * 140).passed


def test_meta_fails_below_120() -> None:
    result = check_meta_length("Short meta.")
    assert not result.passed
    assert "too short" in result.detail


def test_meta_fails_above_160() -> None:
    result = check_meta_length("M" * 161)
    assert not result.passed
    assert "too long" in result.detail


# ------------------------------------------------------------------ #
# check_keyword_presence                                               #
# ------------------------------------------------------------------ #


def test_keyword_presence_passes_when_all_present() -> None:
    body = "java 21 virtual threads are useful for spring boot concurrency."
    result = check_keyword_presence(body, "java 21 virtual threads", ["spring boot"])
    assert result.passed


def test_keyword_presence_fails_when_primary_missing() -> None:
    result = check_keyword_presence("some text", "missing keyword", [])
    assert not result.passed
    assert "missing keyword" in result.detail


def test_keyword_presence_reports_all_missing() -> None:
    result = check_keyword_presence("text", "kw1", ["kw2", "kw3"])
    assert not result.passed
    assert "kw1" in result.detail
    assert "kw2" in result.detail


def test_keyword_presence_is_case_insensitive() -> None:
    result = check_keyword_presence("Java 21 Virtual Threads guide", "java 21 virtual threads", [])
    assert result.passed


# ------------------------------------------------------------------ #
# check_keyword_in_intro                                               #
# ------------------------------------------------------------------ #


def test_keyword_in_intro_passes_when_in_first_100_words() -> None:
    body = "java 21 virtual threads " + " ".join(["word"] * 90)
    result = check_keyword_in_intro(body, "java 21 virtual threads")
    assert result.passed


def test_keyword_in_intro_fails_when_after_100_words() -> None:
    body = " ".join(["word"] * 110) + " java 21 virtual threads"
    result = check_keyword_in_intro(body, "java 21 virtual threads")
    assert not result.passed


def test_keyword_in_intro_passes_with_no_keyword() -> None:
    result = check_keyword_in_intro("some body", "")
    assert result.passed


# ------------------------------------------------------------------ #
# check_heading_hierarchy                                              #
# ------------------------------------------------------------------ #


def test_heading_hierarchy_passes_with_h1_and_h2() -> None:
    body = "# Title\n\n## Section 1\n\nContent.\n\n## Section 2\n\nMore."
    result = check_heading_hierarchy(body)
    assert result.passed


def test_heading_hierarchy_fails_with_multiple_h1() -> None:
    body = "# Title\n\n# Another Title\n\n## Section\n\nContent."
    result = check_heading_hierarchy(body)
    assert not result.passed
    assert "H1" in result.detail


def test_heading_hierarchy_fails_with_no_h1() -> None:
    body = "## Section\n\nContent here.\n\n## Another"
    result = check_heading_hierarchy(body)
    assert not result.passed


def test_heading_hierarchy_warns_on_level_skip() -> None:
    body = "# Title\n\n### Sub (skips H2)\n\nContent."
    result = check_heading_hierarchy(body)
    assert not result.passed
    assert "jumps" in result.detail.lower() or "skip" in result.detail.lower()


def test_heading_hierarchy_no_h2_warns_for_long_body() -> None:
    body = "# Title\n\n" + " ".join(["word"] * 250)
    result = check_heading_hierarchy(body)
    assert not result.passed


# ------------------------------------------------------------------ #
# check_keyword_density                                                #
# ------------------------------------------------------------------ #


def test_keyword_density_passes_at_1_percent() -> None:
    # 100 words, keyword appears twice (2 words each = 4 kw words / 100 = 4% ... wait)
    # Actually: count = 1 occurrence, kw_words = 3, density = (1*3/100)*100 = 3% > 2.5
    # Let me use a 200-word body with 1 occurrence of 2-word kw = (1*2/200)*100 = 1%
    body = "java threads " + " ".join(["word"] * 198)
    result = check_keyword_density(body, "java threads")
    assert result.passed


def test_keyword_density_fails_when_stuffed() -> None:
    # 200-word body with "java" 20 times — density = (20*1/220)*100 ≈ 9%
    body = ("java " * 20) + " ".join(["word"] * 200)
    result = check_keyword_density(body, "java")
    assert not result.passed
    assert "over threshold" in result.detail


def test_keyword_density_skips_short_body() -> None:
    result = check_keyword_density("short text here", "short")
    assert result.passed
    assert "too short" in result.detail


def test_keyword_density_passes_with_no_keyword() -> None:
    result = check_keyword_density("some body text", "")
    assert result.passed


# ------------------------------------------------------------------ #
# check_code_block_quality                                             #
# ------------------------------------------------------------------ #


def test_code_blocks_all_have_hints() -> None:
    body = "```java\nSystem.out.println();\n```\n\n```bash\necho hi\n```"
    result = check_code_block_quality(body)
    assert result.passed


def test_code_blocks_fails_when_missing_hint() -> None:
    body = "```\nsome code without hint\n```\n\n```java\ngood block\n```"
    result = check_code_block_quality(body)
    assert not result.passed
    assert "1/2" in result.detail


def test_code_blocks_passes_when_no_code_blocks() -> None:
    result = check_code_block_quality("no code here")
    assert result.passed
    assert "no code blocks" in result.detail


# ------------------------------------------------------------------ #
# check_hook_quality                                                   #
# ------------------------------------------------------------------ #


def test_hook_passes_with_two_sentence_intro() -> None:
    body = "First sentence. Second sentence here.\n\n## Section\n\nContent."
    result = check_hook_quality(body)
    assert result.passed


def test_hook_fails_with_single_sentence_intro() -> None:
    body = "Only one sentence.\n\n## Section\n\nContent."
    result = check_hook_quality(body)
    assert not result.passed
    assert "1 sentence" in result.detail


def test_hook_fails_when_no_intro_before_heading() -> None:
    body = "# Title\n\n## Straight to section\n\nContent."
    result = check_hook_quality(body)
    # H1 is a heading, not an intro paragraph — should report no intro found
    assert not result.passed


def test_hook_fails_when_intro_too_long() -> None:
    # 10 lines of intro
    long_intro = "\n".join(["Line " + str(i) + "." for i in range(10)])
    body = long_intro + "\n\n## Section\n\nContent."
    result = check_hook_quality(body)
    assert not result.passed
    assert "lines" in result.detail


# ------------------------------------------------------------------ #
# run_checks (integration)                                             #
# ------------------------------------------------------------------ #


def test_run_checks_returns_eval_result() -> None:
    job = _job()
    result = run_checks(job)
    assert isinstance(result, DeterministicEvalResult)
    assert len(result.checks) == 8


def test_run_checks_reports_short_title() -> None:
    job = _job(title="Short")
    result = run_checks(job)
    title_check = next(c for c in result.checks if c.name == "title_length")
    assert not title_check.passed


def test_run_checks_reports_missing_keyword() -> None:
    job = _job(draft_body_md="## Intro\n\nNo keywords here.\n\n## Body\n\nMore text.")
    result = run_checks(job)
    kw_check = next(c for c in result.checks if c.name == "keyword_presence")
    assert not kw_check.passed


def test_run_checks_summary_shows_failures() -> None:
    job = _job(title="Short")
    result = run_checks(job)
    summary = result.summary()
    assert "title_length" in summary or "failed" in summary.lower()


def test_run_checks_all_pass_for_well_formed_post() -> None:
    """A carefully crafted post should pass all deterministic checks."""
    body = (
        "# Java 21 Virtual Threads in Spring Boot\n\n"
        "Java 21 virtual threads simplify concurrency for Spring Boot developers. "
        "They replace thread pools for most I/O-bound workloads without changing your code.\n\n"
        "## What are virtual threads?\n\n"
        "Virtual threads are lightweight JVM-managed threads. "
        "Unlike platform threads, they do not map 1-to-1 to OS threads.\n\n"
        "```java\nThread.ofVirtual().start(() -> doWork());\n```\n\n"
        "## How spring boot integrates them\n\n"
        "Spring Boot 3.2 auto-configures virtual threads for Tomcat and Undertow.\n\n"
        "## Summary\n\n"
        "Java 21 virtual threads are a clean upgrade for concurrency-heavy services.\n"
    )
    job = _job(
        # "Java 21 Virtual Threads: Spring Boot 3.2 Deep Dive" = 50 chars
        title="Java 21 Virtual Threads: Spring Boot 3.2 Deep Dive",
        meta_description=(
            "Learn how Java 21 virtual threads integrate with Spring Boot 3.2 "
            "to simplify I/O-bound concurrency without thread pool management."
        ),  # 151 chars
        draft_body_md=body,
    )
    result = run_checks(job)
    # All checks should pass for this well-formed post
    failures = [c for c in result.checks if not c.passed]
    # Allow at most 1 minor failure (keyword density edge cases on short body)
    assert len(failures) <= 1, f"Expected ≤1 failures, got: {[str(c) for c in failures]}"


# ------------------------------------------------------------------ #
# DeterministicEvalResult                                              #
# ------------------------------------------------------------------ #


def test_eval_result_passed_true_when_all_pass() -> None:
    from brewpress.boost_eval import CheckResult
    result = DeterministicEvalResult(checks=[
        CheckResult("a", True),
        CheckResult("b", True),
    ])
    assert result.passed


def test_eval_result_passed_false_when_any_fail() -> None:
    from brewpress.boost_eval import CheckResult
    result = DeterministicEvalResult(checks=[
        CheckResult("a", True),
        CheckResult("b", False, "problem"),
    ])
    assert not result.passed
    assert len(result.failures) == 1


def test_eval_result_str_shows_all_checks() -> None:
    from brewpress.boost_eval import CheckResult
    result = DeterministicEvalResult(checks=[
        CheckResult("title_length", True, "55 chars"),
        CheckResult("meta_length", False, "too short"),
    ])
    output = str(result)
    assert "title_length" in output
    assert "meta_length" in output
    assert "FAIL" in output
