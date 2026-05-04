"""SEO analysis tools — all deterministic, no LLM.

Every function returns a plain dict so results can be:
  - logged
  - serialized to JSON
  - fed into an LLM prompt as structured context
  - used for pass/fail gating without an LLM judge

Registered names (call via brewpress.tools.call):
    seo.title          check title length and keyword placement
    seo.meta           check meta description length and quality
    seo.keywords       check keyword presence, density, and placement
    seo.headings       check heading hierarchy and structure
    seo.code_blocks    check fenced code blocks for language hints
    seo.full           run all SEO checks and return unified report
"""

from __future__ import annotations

import re
from typing import Any

from brewpress.tools import register

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

_WORD_RE = re.compile(r"\b\w+\b")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)", re.MULTILINE)


def _word_list(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


# ------------------------------------------------------------------ #
# Individual tools                                                     #
# ------------------------------------------------------------------ #


@register("seo.title")
def check_title(title: str) -> dict[str, Any]:
    """Check SEO quality of a post title.

    Args:
        title: Post title string.

    Returns:
        dict with keys: length, in_range, recommendation (str or None)
    """
    n = len(title.strip())
    in_range = 50 <= n <= 60
    rec: str | None = None
    if n < 50:
        rec = f"Title is {n} chars — target 50–60. Expand to include the primary keyword context."
    elif n > 60:
        rec = f"Title is {n} chars — will be truncated in SERPs. Trim to ≤ 60 chars."
    return {"length": n, "in_range": in_range, "recommendation": rec}


@register("seo.meta")
def check_meta(meta: str) -> dict[str, Any]:
    """Check SEO quality of a meta description.

    Args:
        meta: Meta description string.

    Returns:
        dict with keys: length, in_range, recommendation (str or None)
    """
    n = len(meta.strip())
    in_range = 120 <= n <= 160
    rec: str | None = None
    if n < 120:
        rec = (
            f"Meta is {n} chars — under-utilises SERP space (target 120–160). "
            "Add a brief outcome statement."
        )
    elif n > 160:
        rec = f"Meta is {n} chars — will be cut off in SERPs. Trim to ≤ 160 chars."
    return {"length": n, "in_range": in_range, "recommendation": rec}


@register("seo.keywords")
def check_keywords(
    body: str,
    primary: str,
    secondary: list[str] | None = None,
) -> dict[str, Any]:
    """Analyse keyword presence, placement, and density.

    Args:
        body:      Post body text (Markdown or plain).
        primary:   Primary SEO keyword.
        secondary: List of secondary keywords (optional).

    Returns:
        dict with keys: found, missing, density_pct, in_intro, issues
    """
    body_lower = body.lower()
    words = _word_list(body)
    total_words = len(words)
    all_kws = ([primary] if primary else []) + list(secondary or [])

    found = [kw for kw in all_kws if kw and kw.lower() in body_lower]
    missing = [kw for kw in all_kws if kw and kw.lower() not in body_lower]

    # Keyword density for primary
    density_pct: float = 0.0
    if primary and total_words >= 100:
        count = body_lower.count(primary.lower())
        kw_word_count = len(primary.split())
        density_pct = round((count * kw_word_count / total_words) * 100, 2)

    # In intro (first 100 words)
    intro_text = " ".join(words[:100])
    in_intro = bool(primary) and primary.lower() in intro_text

    issues: list[str] = []
    if missing:
        issues.append(f"Missing keywords: {', '.join(missing)}")
    if primary and total_words >= 100:
        if density_pct > 2.5:
            issues.append(f"Keyword stuffing: '{primary}' density {density_pct:.1f}% > 2.5%")
        elif density_pct < 0.5:
            issues.append(f"Under-usage: '{primary}' density {density_pct:.1f}% < 0.5%")
    if primary and not in_intro:
        issues.append(f"'{primary}' not found in first 100 words — move it to the intro.")

    return {
        "found": found,
        "missing": missing,
        "density_pct": density_pct,
        "in_intro": in_intro,
        "issues": issues,
        "total_words": total_words,
    }


@register("seo.headings")
def check_headings(body: str) -> dict[str, Any]:
    """Analyse heading hierarchy for SEO and accessibility.

    Args:
        body: Post body (Markdown).

    Returns:
        dict with keys: h1_count, h2_count, h3_count, issues, summary
    """
    headings = _HEADING_RE.findall(body)
    counts: dict[str, int] = {f"h{i}": 0 for i in range(1, 7)}
    for level, _ in headings:
        counts[f"h{len(level)}"] += 1

    issues: list[str] = []
    levels = [len(level) for level, _ in headings]

    if counts["h1"] == 0:
        issues.append("No H1 found — add one top-level title.")
    if counts["h1"] > 1:
        issues.append(f"H1 appears {counts['h1']}× — use exactly one H1.")
    if counts["h2"] == 0 and len(" ".join(_word_list(body))) > 200:
        issues.append("No H2 sections — break content into sections with H2 headings.")

    for i in range(1, len(levels)):
        if levels[i] - levels[i - 1] > 1:
            issues.append(
                f"Heading jumps H{levels[i-1]}→H{levels[i]} — do not skip levels."
            )
            break

    return {
        "h1_count": counts["h1"],
        "h2_count": counts["h2"],
        "h3_count": counts["h3"],
        "issues": issues,
        "summary": (
            f"H1×{counts['h1']} H2×{counts['h2']} H3×{counts['h3']}"
            + (f" — {len(issues)} issue(s)" if issues else " — OK")
        ),
    }


@register("seo.code_blocks")
def check_code_blocks(body: str) -> dict[str, Any]:
    """Check that fenced code blocks have a language hint.

    Args:
        body: Post body (Markdown).

    Returns:
        dict with keys: total, missing_hint, issues
    """
    all_fences = _CODE_FENCE_RE.findall(body)
    opening_fences = all_fences[::2]  # odd-indexed are closing fences
    total = len(opening_fences)
    missing_hint = sum(1 for lang in opening_fences if not lang.strip())

    issues: list[str] = []
    if missing_hint > 0:
        issues.append(
            f"{missing_hint}/{total} code block(s) missing language hint — "
            "add e.g. ```java, ```bash, ```python"
        )

    return {
        "total": total,
        "missing_hint": missing_hint,
        "issues": issues,
    }


@register("seo.full")
def full_seo_check(
    title: str,
    meta: str,
    body: str,
    primary_keyword: str,
    secondary_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Run all SEO checks and return a unified report.

    This is the high-level tool that agents call when they want a full SEO
    picture without calling each tool individually.

    Returns:
        dict with keys: passed (bool), score (int 0-100), checks (dict of sub-results)
    """
    title_result = check_title(title)
    meta_result = check_meta(meta)
    kw_result = check_keywords(body, primary_keyword, secondary_keywords or [])
    heading_result = check_headings(body)
    code_result = check_code_blocks(body)

    all_issues: list[str] = (
        ([title_result["recommendation"]] if title_result["recommendation"] else [])
        + ([meta_result["recommendation"]] if meta_result["recommendation"] else [])
        + kw_result["issues"]
        + heading_result["issues"]
        + code_result["issues"]
    )

    # Simple 0-100 score: each dimension worth 20 points
    score = 100
    score -= 0 if title_result["in_range"] else 20
    score -= 0 if meta_result["in_range"] else 15
    score -= min(len(kw_result["missing"]) * 10, 25)
    score -= min(len(heading_result["issues"]) * 10, 20)
    score -= 0 if code_result["missing_hint"] == 0 else 10
    score = max(0, score)

    return {
        "passed": score >= 60,
        "score": score,
        "issues": all_issues,
        "checks": {
            "title": title_result,
            "meta": meta_result,
            "keywords": kw_result,
            "headings": heading_result,
            "code_blocks": code_result,
        },
    }
