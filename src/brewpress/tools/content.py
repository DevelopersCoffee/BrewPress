"""Content analysis tools — deterministic, no LLM.

These tools extract structure and signals from Markdown content.
Agents call these before deciding whether an LLM judgment is needed.

Registered names (call via brewpress.tools.call):
    content.word_count        count words in text
    content.headings          extract all headings with level + text
    content.code_blocks       extract all code blocks with language + body
    content.hook              analyse the opening paragraph (hook quality)
    content.paragraphs        check paragraph length distribution
    content.structure_summary full structural summary in one call
"""

from __future__ import annotations

import re
from typing import Any

from brewpress.tools import register

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_WORD_RE = re.compile(r"\b\w+\b")


# ------------------------------------------------------------------ #
# Tools                                                                #
# ------------------------------------------------------------------ #


@register("content.word_count")
def word_count(text: str) -> int:
    """Count words in a text string.

    Args:
        text: Any text (Markdown or plain).

    Returns:
        Word count as an integer.
    """
    return len(_WORD_RE.findall(text))


@register("content.headings")
def extract_headings(body: str) -> list[dict[str, Any]]:
    """Extract all headings from Markdown with their level and text.

    Args:
        body: Markdown body text.

    Returns:
        List of dicts: [{"level": 2, "text": "Introduction"}, ...]
    """
    return [
        {"level": len(level), "text": text.strip()}
        for level, text in _HEADING_RE.findall(body)
    ]


@register("content.code_blocks")
def extract_code_blocks(body: str) -> list[dict[str, Any]]:
    """Extract all fenced code blocks with language hint and content.

    Args:
        body: Markdown body text.

    Returns:
        List of dicts: [{"language": "java", "code": "...", "line_count": 5}, ...]
    """
    blocks = []
    for lang, code in _CODE_FENCE_RE.findall(body):
        lines = [l for l in code.splitlines() if l.strip()]
        blocks.append({
            "language": lang.strip() or None,
            "code": code.strip(),
            "line_count": len(lines),
            "has_language_hint": bool(lang.strip()),
        })
    return blocks


@register("content.hook")
def analyse_hook(body: str) -> dict[str, Any]:
    """Analyse the quality of the opening hook paragraph.

    The hook is the first non-heading paragraph. A good hook:
    - Has 2–3 sentences
    - Is ≤ 8 lines
    - States the problem or what the reader will learn

    Args:
        body: Markdown body text.

    Returns:
        dict with keys: text, sentence_count, line_count, passed, issues
    """
    paragraphs = re.split(r"\n\n+", body.strip())
    first_para = ""
    for para in paragraphs:
        stripped = para.strip()
        if stripped and not stripped.startswith("#"):
            first_para = stripped
            break

    if not first_para:
        return {
            "text": "",
            "sentence_count": 0,
            "line_count": 0,
            "passed": False,
            "issues": ["No intro paragraph found before the first heading."],
        }

    sentences = re.split(r"(?<=[.!?])\s+", first_para)
    sentence_count = len([s for s in sentences if len(s.strip()) > 4])
    line_count = len(first_para.splitlines())

    issues: list[str] = []
    if sentence_count < 2:
        issues.append(
            f"Hook has {sentence_count} sentence(s) — lead with 2–3 sentences that "
            "state the problem and what the reader will learn."
        )
    if line_count > 8:
        issues.append(
            f"Hook is {line_count} lines — keep it tight (≤ 8 lines)."
        )

    return {
        "text": first_para[:300],
        "sentence_count": sentence_count,
        "line_count": line_count,
        "passed": not issues,
        "issues": issues,
    }


@register("content.paragraphs")
def check_paragraphs(body: str) -> dict[str, Any]:
    """Check paragraph length distribution.

    Short paragraphs (2–3 sentences) improve readability. Flag long ones.

    Args:
        body: Markdown body text (H-less paragraphs are analysed).

    Returns:
        dict with keys: total, too_long (list of paragraph previews), passed
    """
    paragraphs = re.split(r"\n\n+", body.strip())
    content_paras = [
        p.strip() for p in paragraphs
        if p.strip() and not p.strip().startswith("#")
    ]
    too_long = []
    for para in content_paras:
        sentences = re.split(r"(?<=[.!?])\s+", para)
        sentence_count = len([s for s in sentences if len(s.strip()) > 4])
        if sentence_count > 5:
            too_long.append({
                "preview": para[:80],
                "sentence_count": sentence_count,
            })

    return {
        "total": len(content_paras),
        "too_long": too_long,
        "passed": len(too_long) == 0,
        "issues": (
            [f"{len(too_long)} paragraph(s) exceed 5 sentences — break them up."]
            if too_long else []
        ),
    }


@register("content.structure_summary")
def structure_summary(body: str, title: str = "", meta: str = "") -> dict[str, Any]:
    """Return a full structural summary of a post in one call.

    Combines all content analysis tools. Agents call this when they need
    a complete picture before deciding whether to escalate to LLM.

    Args:
        body:  Markdown body.
        title: Post title (optional, for word count + hook context).
        meta:  Meta description (optional).

    Returns:
        dict with keys: word_count, headings, code_blocks, hook, paragraphs,
                        has_cta, issues (aggregated)
    """
    wc = word_count(body)
    headings = extract_headings(body)
    code_blocks = extract_code_blocks(body)
    hook = analyse_hook(body)
    paragraphs = check_paragraphs(body)

    # Simple CTA detection: last paragraph contains a call-to-action signal
    paras = [p.strip() for p in re.split(r"\n\n+", body.strip()) if p.strip()]
    last_para = paras[-1] if paras else ""
    cta_signals = ["try", "next step", "challenge", "give it a go", "reach out", "let me know"]
    has_cta = any(sig in last_para.lower() for sig in cta_signals)

    all_issues: list[str] = hook["issues"] + paragraphs["issues"]
    if not has_cta and wc > 300:
        all_issues.append("No CTA detected in last paragraph — add a clear next step.")

    return {
        "word_count": wc,
        "heading_count": len(headings),
        "h1_count": sum(1 for h in headings if h["level"] == 1),
        "h2_count": sum(1 for h in headings if h["level"] == 2),
        "code_block_count": len(code_blocks),
        "code_with_hints": sum(1 for b in code_blocks if b["has_language_hint"]),
        "hook": hook,
        "has_cta": has_cta,
        "issues": all_issues,
        "passed": not all_issues,
    }
