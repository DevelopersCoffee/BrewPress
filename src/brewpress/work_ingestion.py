"""Work Ingestion — normalize draft inputs into a typed WorkContext.

Accepts the three MVP input surfaces from the PRD and produces a single
WorkContext that the generation agent consumes:

    topic + notes   — always required
    local git diff  — path to a unified diff file
    GitHub PR URL   — Phase 2 placeholder (accepted, not fetched)

Content-type detection (PRD §Content Types):
    Code Post:  diff present  OR  PR URL present  OR  runnable commands found
    Idea Post:  topic only, no code proof — is_code_post=False

Repo URL input is out of scope for MVP.

ADK integration note: ingest() maps cleanly to an ADK Tool call.
WorkContext is the typed grounding input consumed by the Draft Agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ------------------------------------------------------------------ #
# Data models                                                          #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class DiffHunk:
    """One contiguous change block within a single file."""

    file_path: str
    header: str        # raw "@@ -n,m +n,m @@" line, preserved for grounding
    removed: list[str]  # lines that were deleted (without leading "-")
    added: list[str]    # lines that were added   (without leading "+")


@dataclass(frozen=True)
class ParsedDiff:
    """Structured representation of a unified diff."""

    hunks: list[DiffHunk]
    files_changed: list[str]  # ordered, deduplicated file paths
    raw: str                  # original text, preserved verbatim for grounding


@dataclass(frozen=True)
class WorkContext:
    """All normalized inputs for one blog-generation job.

    Consumed by the Draft Agent (Stack 4) as its sole grounding input.
    """

    topic: str
    notes: str
    diff: ParsedDiff | None   # None when no diff was provided
    pr_url: str | None        # Phase 2 — accepted but not fetched in MVP
    commands: list[str]       # runnable shell commands extracted from inputs
    is_code_post: bool        # PRD §Content Types classification


# ------------------------------------------------------------------ #
# Diff parsing                                                         #
# ------------------------------------------------------------------ #

# @@ -old_start[,old_count] +new_start[,new_count] @@ [context]
_HUNK_HEADER_RE = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@")

# diff --git a/<path> b/<path>
_GIT_FILE_RE = re.compile(r"^diff --git a/.+ b/(.+)$")

# +++ b/<path>  or  +++ <path>
_PLUS_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")


def _flush(
    hunks: list[DiffHunk],
    file_path: str,
    header: str,
    removed: list[str],
    added: list[str],
) -> None:
    """Append a completed hunk to the list (no-op if file or header is empty)."""
    if file_path and header:
        hunks.append(DiffHunk(
            file_path=file_path,
            header=header,
            removed=removed,
            added=added,
        ))


def parse_diff(raw: str) -> ParsedDiff:
    """Parse unified diff text into a ParsedDiff.

    Handles both plain unified diff and git diff format.  Returns a
    ParsedDiff with empty hunks for an empty or whitespace-only input.

    Does not validate line counts; malformed hunks are included as-is so
    that the generation agent still receives whatever grounding is available.
    """
    if not raw.strip():
        return ParsedDiff(hunks=[], files_changed=[], raw=raw)

    hunks: list[DiffHunk] = []
    files_seen: list[str] = []
    files_set: set[str] = set()

    cur_file = ""
    cur_header = ""
    cur_removed: list[str] = []
    cur_added: list[str] = []
    in_hunk = False

    def register_file(path: str) -> None:
        nonlocal cur_file
        cur_file = path
        if path not in files_set:
            files_set.add(path)
            files_seen.append(path)

    for line in raw.splitlines():

        # ── git diff file boundary ─────────────────────────────────
        m = _GIT_FILE_RE.match(line)
        if m:
            _flush(hunks, cur_file, cur_header, cur_removed, cur_added)
            in_hunk = False
            cur_header = ""
            cur_removed = []
            cur_added = []
            register_file(m.group(1))
            continue

        # ── plain unified diff "+++ b/path" (only outside a hunk) ──
        if line.startswith("+++ ") and not in_hunk:
            m2 = _PLUS_FILE_RE.match(line)
            if m2:
                candidate = m2.group(1)
                if candidate != "/dev/null":
                    register_file(candidate)
            continue

        # ── hunk header ─────────────────────────────────────────────
        if _HUNK_HEADER_RE.match(line):
            _flush(hunks, cur_file, cur_header, cur_removed, cur_added)
            in_hunk = True
            cur_header = line
            cur_removed = []
            cur_added = []
            continue

        # ── diff body lines ─────────────────────────────────────────
        if in_hunk:
            if line.startswith("-") and not line.startswith("---"):
                cur_removed.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                cur_added.append(line[1:])
            # context lines (space prefix or empty) are skipped

    # flush final hunk
    _flush(hunks, cur_file, cur_header, cur_removed, cur_added)

    return ParsedDiff(hunks=hunks, files_changed=files_seen, raw=raw)


# ------------------------------------------------------------------ #
# Command extraction                                                   #
# ------------------------------------------------------------------ #

# A line that starts with "$ " is treated as an explicit shell command.
# This is conservative: no invented commands, no heuristics beyond the marker.
_SHELL_PROMPT_RE = re.compile(r"^\s*\$\s+(.+)$")


def extract_commands(notes: str, diff: ParsedDiff | None = None) -> list[str]:
    """Extract runnable shell commands from notes text and diff added lines.

    Only lines explicitly marked with a leading ``$ `` are extracted.
    This ensures no commands are invented — only what the user provided.

    Deduplication is applied; order of first appearance is preserved.
    """
    commands: list[str] = []
    seen: set[str] = set()

    def collect(line: str) -> None:
        m = _SHELL_PROMPT_RE.match(line)
        if m:
            cmd = m.group(1).strip()
            if cmd and cmd not in seen:
                seen.add(cmd)
                commands.append(cmd)

    for line in notes.splitlines():
        collect(line)

    if diff:
        for hunk in diff.hunks:
            for added_line in hunk.added:
                collect(added_line)

    return commands


# ------------------------------------------------------------------ #
# Code-post detection                                                  #
# ------------------------------------------------------------------ #


def detect_code_post(
    diff: ParsedDiff | None,
    pr_url: str | None,
    commands: list[str],
) -> bool:
    """Return True when the job qualifies as a Code Post (PRD §Content Types).

    A job is a Code Post if any of:
    - a diff with at least one hunk is present
    - a PR URL is present
    - at least one runnable command was extracted
    """
    if diff is not None and diff.hunks:
        return True
    if pr_url:
        return True
    if commands:
        return True
    return False


# ------------------------------------------------------------------ #
# Main entry point                                                     #
# ------------------------------------------------------------------ #


def ingest(
    topic: str,
    notes: str = "",
    diff_path: str | None = None,
    pr_url: str | None = None,
) -> WorkContext:
    """Normalize all inputs for one blog-generation job into a WorkContext.

    Args:
        topic:     Blog topic or angle. Stripped of leading/trailing whitespace.
        notes:     Work notes or additional context. May be empty.
        diff_path: Path to a local unified diff file. Mutually exclusive with
                   repo URL (which is out of scope for MVP).
        pr_url:    GitHub PR URL. Accepted and stored; not fetched in MVP.

    Returns:
        WorkContext with all inputs normalized and is_code_post set.

    Raises:
        FileNotFoundError: diff_path provided but the file does not exist.
        OSError:           diff_path provided but the file cannot be read.
    """
    topic = topic.strip()
    notes = notes.strip()

    diff: ParsedDiff | None = None
    if diff_path is not None:
        raw = Path(diff_path).read_text(encoding="utf-8")
        diff = parse_diff(raw)

    commands = extract_commands(notes, diff)
    is_code_post = detect_code_post(diff, pr_url, commands)

    return WorkContext(
        topic=topic,
        notes=notes,
        diff=diff,
        pr_url=pr_url,
        commands=commands,
        is_code_post=is_code_post,
    )
