"""Strip pipeline-scaffolding sections from a draft body before publish.

Some drafts (especially executed-tutorial posts) carry sections that exist
only so downstream tooling can re-run commands and capture proof. Those
sections must not reach readers. This module removes them by H2 heading.

Sections stripped (case-insensitive H2 match):
    ## Executed Tutorial Steps
    ## Execution Proof
    ## Screenshot Plan for the Blog Pipeline

Each scaffolding H2 section is removed from its heading line up to (but
not including) the next H1 OR H2 heading, or EOF. The function is
idempotent: running it twice yields the same result as running it once.
"""

from __future__ import annotations

import re

_STRIP_HEADINGS = (
    "executed tutorial steps",
    "execution proof",
    "screenshot plan for the blog pipeline",
)

# H1 or H2 heading line: '#' or '##' followed by a space and the title.
# We capture the level so callers can distinguish; the heading-level group
# is `level` (1 or 2). H3+ are deliberately not matched — section nesting
# inside a stripped H2 should be removed along with it.
_H1H2_RE = re.compile(r"^(?P<hashes>#{1,2})\s+(?P<title>.+?)\s*$", re.MULTILINE)


def sanitize_body_for_publish(body_md: str) -> str:
    """Remove pipeline-scaffolding sections from a Markdown body.

    Args:
        body_md: Raw Markdown body. Frontmatter must already be stripped.

    Returns:
        Body with scaffolding sections removed. Other sections preserved
        verbatim. Idempotent.
    """
    if not body_md:
        return body_md

    headings = list(_H1H2_RE.finditer(body_md))
    if not headings:
        return body_md

    # Build [(start, end, title_lower, level), ...] for every H1/H2 heading.
    # `end` is the start of the next H1/H2 (regardless of level) or EOF.
    # This ensures stripping an H2 scaffolding section never reaches across
    # an intervening H1 boundary.
    spans: list[tuple[int, int, str, int]] = []
    for i, m in enumerate(headings):
        start = m.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body_md)
        title = m.group("title").strip().lower()
        level = len(m.group("hashes"))
        spans.append((start, end, title, level))

    # Only H2 scaffolding sections are eligible for removal. H1 boundaries
    # always terminate a stripped span (handled implicitly because every
    # H1/H2 starts a new entry in `spans`).
    if not any(t in _STRIP_HEADINGS and lvl == 2 for _, _, t, lvl in spans):
        return body_md  # no-op fast path

    keep: list[tuple[int, int]] = []
    cursor = 0
    for start, end, title, level in spans:
        if level == 2 and title in _STRIP_HEADINGS:
            if cursor < start:
                keep.append((cursor, start))
            cursor = end
    if cursor < len(body_md):
        keep.append((cursor, len(body_md)))

    cleaned = "".join(body_md[s:e] for s, e in keep)

    # Collapse runs of 3+ blank lines that may appear at section seams.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"
