"""Boost Eval — deterministic (no-API) quality checks for blog post content.

Complements CriticAgent (LLM-based) with fast, zero-cost heuristic checks
that catch obvious problems before burning API tokens.

All checks operate on plain strings — no external dependencies beyond the
standard library.  Results are structured so callers can display them,
log them, or gate on them.

Checks:
    keyword_presence    — primary/secondary keywords appear in the body
    title_length        — 50–60 characters recommended
    meta_length         — 120–160 characters recommended
    heading_hierarchy   — H1 count = 1, H2 present, no skipped levels
    keyword_density     — primary keyword density 0.5–2.5% (stuffing guard)
    code_block_quality  — fenced blocks have a language hint
    hook_quality        — intro paragraph is ≥ 2 sentences and < 5 lines

Run all checks via: run_checks(job) → DeterministicEvalResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from brewpress.models import BlogJob

# ------------------------------------------------------------------ #
# Individual check results                                             #
# ------------------------------------------------------------------ #


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:
        icon = "OK  " if self.passed else "FAIL"
        msg = f"[{icon}] {self.name}"
        if self.detail:
            msg += f" — {self.detail}"
        return msg


# ------------------------------------------------------------------ #
# Aggregated result                                                    #
# ------------------------------------------------------------------ #


@dataclass
class DeterministicEvalResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        total = len(self.checks)
        failed = len(self.failures)
        if failed == 0:
            return f"All {total} deterministic checks passed."
        return f"{failed}/{total} checks failed: {', '.join(c.name for c in self.failures)}"

    def __str__(self) -> str:
        return "\n".join(str(c) for c in self.checks)


# ------------------------------------------------------------------ #
# Individual check functions                                           #
# ------------------------------------------------------------------ #

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)", re.MULTILINE)
_WORD_RE = re.compile(r"\b\w+\b")


def check_title_length(title: str) -> CheckResult:
    n = len(title.strip())
    if 50 <= n <= 60:
        return CheckResult("title_length", True, f"{n} chars")
    detail = f"{n} chars — target 50–60"
    if n < 50:
        detail += "; too short, may be weak for SEO"
    else:
        detail += "; too long, may be truncated in SERPs"
    return CheckResult("title_length", False, detail)


def check_meta_length(meta: str) -> CheckResult:
    n = len(meta.strip())
    if 120 <= n <= 160:
        return CheckResult("meta_length", True, f"{n} chars")
    detail = f"{n} chars — target 120–160"
    if n < 120:
        detail += "; too short, under-utilises SERP space"
    else:
        detail += "; too long, will be truncated"
    return CheckResult("meta_length", False, detail)


def check_keyword_presence(body: str, primary: str, secondary: list[str]) -> CheckResult:
    body_lower = body.lower()
    missing: list[str] = []

    if primary and primary.lower() not in body_lower:
        missing.append(primary)

    for kw in (secondary or []):
        if kw and kw.lower() not in body_lower:
            missing.append(kw)

    if not missing:
        return CheckResult("keyword_presence", True)
    return CheckResult(
        "keyword_presence", False,
        f"missing: {', '.join(missing)}"
    )


def check_keyword_in_intro(body: str, primary: str) -> CheckResult:
    """Primary keyword should appear in the first ~100 words."""
    if not primary:
        return CheckResult("keyword_in_intro", True, "no primary keyword specified")
    words = _WORD_RE.findall(body)
    intro_text = " ".join(words[:100]).lower()
    if primary.lower() in intro_text:
        return CheckResult("keyword_in_intro", True)
    return CheckResult(
        "keyword_in_intro", False,
        f"'{primary}' not found in the first 100 words — move it to the intro"
    )


def check_heading_hierarchy(body: str) -> CheckResult:
    headings = _HEADING_RE.findall(body)
    issues: list[str] = []

    h1_count = sum(1 for level, _ in headings if level == "#")
    h2_count = sum(1 for level, _ in headings if level == "##")

    if h1_count > 1:
        issues.append(f"H1 appears {h1_count}× — use exactly one H1")
    if h1_count == 0:
        issues.append("no H1 found — add a top-level title")
    if h2_count == 0 and len(body.split()) > 200:
        issues.append("no H2 sections — add section headings to guide readers")

    # Check for skipped levels (H1 → H3 without H2)
    levels = [len(level) for level, _ in headings]
    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 1:
            issues.append(
                f"heading level jumps from H{levels[i-1]} to H{levels[i]} — "
                "do not skip heading levels"
            )
            break  # report once

    if not issues:
        return CheckResult("heading_hierarchy", True, f"H1×{h1_count} H2×{h2_count}")
    return CheckResult("heading_hierarchy", False, "; ".join(issues))


def check_keyword_density(body: str, primary: str) -> CheckResult:
    """Primary keyword density should be 0.5–2.5% (stuffing guard)."""
    if not primary:
        return CheckResult("keyword_density", True, "no primary keyword specified")
    words = _WORD_RE.findall(body.lower())
    total_words = len(words)
    if total_words < 100:
        return CheckResult("keyword_density", True, "body too short to measure")

    kw_words = len(primary.lower().split())
    # Count non-overlapping occurrences
    count = body.lower().count(primary.lower())
    density = (count * kw_words / total_words) * 100

    if 0.5 <= density <= 2.5:
        return CheckResult("keyword_density", True, f"{density:.1f}%")
    if density > 2.5:
        return CheckResult(
            "keyword_density", False,
            f"{density:.1f}% — over threshold (2.5%); reduce keyword repetition"
        )
    return CheckResult(
        "keyword_density", False,
        f"{density:.1f}% — under threshold (0.5%); use keyword more naturally"
    )


def check_code_block_quality(body: str) -> CheckResult:
    """Every fenced code block should have a language hint."""
    all_fences = _CODE_FENCE_RE.findall(body)
    if not all_fences:
        return CheckResult("code_block_quality", True, "no code blocks")
    # Fences alternate: opening (even index), closing (odd index).
    # Only opening fences should have a language hint.
    opening_fences = all_fences[::2]
    missing_lang = sum(1 for lang in opening_fences if not lang.strip())
    if missing_lang == 0:
        return CheckResult(
            "code_block_quality", True, f"{len(opening_fences)} block(s) with hints"
        )
    return CheckResult(
        "code_block_quality", False,
        f"{missing_lang}/{len(opening_fences)} code block(s) missing language hint"
        " — add e.g. ```java"
    )


def check_hook_quality(body: str) -> CheckResult:
    """Intro paragraph should be 2+ sentences and reasonably short."""
    # Split on first blank line to get the intro
    paragraphs = re.split(r"\n\n+", body.strip())
    first_para = ""
    for para in paragraphs:
        stripped = para.strip()
        if stripped and not stripped.startswith("#"):
            first_para = stripped
            break

    if not first_para:
        return CheckResult("hook_quality", False, "no intro paragraph found before first heading")

    sentences = re.split(r"(?<=[.!?])\s+", first_para)
    sentence_count = len([s for s in sentences if len(s.strip()) > 4])
    line_count = len(first_para.splitlines())

    if sentence_count < 2:
        return CheckResult(
            "hook_quality", False,
            f"intro has {sentence_count} sentence(s) — lead with ≥ 2 sentences"
        )
    if line_count > 8:
        return CheckResult(
            "hook_quality", False,
            f"intro is {line_count} lines — keep the hook tight (≤ 8 lines)"
        )
    return CheckResult("hook_quality", True, f"{sentence_count} sentences")


# ------------------------------------------------------------------ #
# Runner                                                               #
# ------------------------------------------------------------------ #


def run_checks(job: BlogJob) -> DeterministicEvalResult:
    """Run all deterministic checks against a BlogJob.

    Args:
        job: Any BlogJob (DRAFT state recommended — checks do not alter state).

    Returns:
        DeterministicEvalResult with per-check pass/fail and a summary.
    """
    body = job.draft_body_md or ""
    title = job.title or ""
    meta = job.meta_description or ""
    primary = job.primary_keyword or ""
    secondary = list(job.secondary_keywords or [])

    checks: list[CheckResult] = [
        check_title_length(title),
        check_meta_length(meta),
        check_keyword_presence(body, primary, secondary),
        check_keyword_in_intro(body, primary),
        check_heading_hierarchy(body),
        check_keyword_density(body, primary),
        check_code_block_quality(body),
        check_hook_quality(body),
    ]

    return DeterministicEvalResult(checks=checks)
