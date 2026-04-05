"""Media Agent — terminal and output proof screenshots for code posts.

Takes a CommandResult from the Execution Layer and renders two PNG screenshots:

    TERMINAL_SCREENSHOT  — shows the command prompt + first N lines of output.
                           Proof that the command was run.

    OUTPUT_PROOF         — shows the full stdout/stderr.
                           Proof that the output matches what is claimed.

PRD §Media Agent (MVP):
    - terminal screenshot (at least 1 per code post)
    - output proof screenshot (at least 1 per code post)
    - no video generation
    - no browser UI screenshot in MVP

PRD §Screenshot Rule:
    Code posts must include:
        1 terminal + 1 output proof  ← definition of done

validate_code_post_media() enforces this contract and returns human-readable
gap messages that feed directly into the revise loop.

ADK integration note: capture_screenshot() and generate_for_code_post()
map cleanly to ADK Tool calls once the full pipeline is wired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from brewpress.execution_layer import CommandResult, ExecutionTrace

# ------------------------------------------------------------------ #
# Font loading                                                         #
# ------------------------------------------------------------------ #

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",         # macOS
    "/System/Library/Fonts/Monaco.ttf",        # macOS (older)
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/cour.ttf",               # Windows
]


def _load_font(size: int = 13) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # Pillow ≥10: load_default accepts a size kwarg
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ #
# Colour palette (dark terminal theme)                                #
# ------------------------------------------------------------------ #

_BG = (28, 28, 28)
_PROMPT_FG = (80, 220, 100)     # green — for "$ command" lines
_OUTPUT_FG = (200, 200, 200)    # light grey — stdout
_STDERR_FG = (255, 130, 60)     # orange — stderr
_HEADER_FG = (120, 180, 255)    # blue — title bar
_SEPARATOR = (55, 55, 55)

_LINE_HEIGHT = 18
_PADDING = 14
_HEADER_HEIGHT = 32
_IMAGE_WIDTH = 920
_MAX_LINE_CHARS = 120
_MAX_LINES = 60


# ------------------------------------------------------------------ #
# Data models                                                          #
# ------------------------------------------------------------------ #


class MediaType(StrEnum):
    TERMINAL_SCREENSHOT = "terminal_screenshot"
    OUTPUT_PROOF = "output_proof"


@dataclass(frozen=True)
class MediaItem:
    """One captured screenshot associated with a command result."""

    path: Path
    media_type: MediaType
    command: str
    caption: str


@dataclass(frozen=True)
class MediaManifest:
    """All media captured for one blog-generation job.

    Passed to the WordPress client (Stack 6) for media upload and
    to generate_failure_bundle() for the local fallback bundle.
    """

    job_id: str
    items: list[MediaItem] = field(default_factory=list)

    @property
    def has_terminal_screenshot(self) -> bool:
        return any(i.media_type == MediaType.TERMINAL_SCREENSHOT for i in self.items)

    @property
    def has_output_proof(self) -> bool:
        return any(i.media_type == MediaType.OUTPUT_PROOF for i in self.items)

    def by_type(self, media_type: MediaType) -> list[MediaItem]:
        return [i for i in self.items if i.media_type == media_type]


# ------------------------------------------------------------------ #
# Image rendering                                                      #
# ------------------------------------------------------------------ #


def _truncate_lines(lines: list[str], max_lines: int = _MAX_LINES) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept.append(f"... [{len(lines) - max_lines} more lines truncated]")
    return kept


def _line_colour(line: str, is_stderr: bool = False) -> tuple[int, int, int]:
    if is_stderr:
        return _STDERR_FG
    if re.match(r"^\s*\$\s+\S", line):
        return _PROMPT_FG
    return _OUTPUT_FG


def render_terminal_image(
    lines: list[str],
    title: str = "",
    *,
    stderr_lines: list[str] | None = None,
    width: int = _IMAGE_WIDTH,
) -> bytes:
    """Render text lines to a dark-theme terminal PNG.

    Args:
        lines:        Text lines to render (stdout or mixed command+output).
        title:        Optional header text shown above the separator.
        stderr_lines: When provided, rendered in orange after stdout.
        width:        Image width in pixels.

    Returns:
        PNG image as raw bytes.
    """
    font = _load_font(13)
    stderr_lines = stderr_lines or []

    visible = _truncate_lines(lines)
    if stderr_lines:
        visible += ["--- stderr ---"] + _truncate_lines(stderr_lines, 20)

    height = (
        _HEADER_HEIGHT
        + _PADDING
        + _LINE_HEIGHT * max(len(visible), 3)
        + _PADDING
    )

    img = Image.new("RGB", (width, height), color=_BG)
    draw = ImageDraw.Draw(img)

    # ── header bar ──────────────────────────────────────────────────
    draw.rectangle([(0, 0), (width, _HEADER_HEIGHT)], fill=(40, 40, 40))
    draw.text((_PADDING, 8), title or "Terminal", fill=_HEADER_FG, font=font)
    draw.line([(0, _HEADER_HEIGHT), (width, _HEADER_HEIGHT)], fill=_SEPARATOR)

    # ── body lines ──────────────────────────────────────────────────
    y = _HEADER_HEIGHT + _PADDING
    for raw_line in visible:
        display = raw_line[:_MAX_LINE_CHARS]
        is_stderr = raw_line == "--- stderr ---" or (
            stderr_lines and raw_line in stderr_lines
        )
        colour = _line_colour(raw_line, is_stderr)
        draw.text((_PADDING, y), display, fill=colour, font=font)
        y += _LINE_HEIGHT

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ #
# Screenshot capture                                                   #
# ------------------------------------------------------------------ #


def _safe_slug(text: str, max_len: int = 30) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:max_len].strip("_")


def capture_screenshot(
    result: CommandResult,
    output_dir: Path,
    media_type: MediaType,
) -> MediaItem:
    """Render a CommandResult to a PNG screenshot file.

    TERMINAL_SCREENSHOT shows the command prompt + first 25 output lines.
    OUTPUT_PROOF shows the full stdout (and stderr if present).

    Args:
        result:     The command result to visualise.
        output_dir: Directory to write the PNG file.
        media_type: Which kind of screenshot to generate.

    Returns:
        MediaItem pointing at the written PNG.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd_slug = _safe_slug(result.command)
    date_prefix = result.ran_at[:10]  # YYYY-MM-DD

    if media_type == MediaType.TERMINAL_SCREENSHOT:
        lines = [f"$ {result.command.strip()}"]
        lines += result.stdout.splitlines()[:25]
        title = "Terminal"
        fname = f"terminal_{date_prefix}_{cmd_slug}.png"
        caption = f"Running: {result.command.strip()}"
    else:
        lines = result.stdout.splitlines()
        title = "Output"
        fname = f"output_{date_prefix}_{cmd_slug}.png"
        caption = f"Output of: {result.command.strip()}"

    png = render_terminal_image(
        lines,
        title=title,
        stderr_lines=result.stderr.splitlines() if result.stderr else None,
    )
    path = output_dir / fname
    path.write_bytes(png)

    return MediaItem(path=path, media_type=media_type, command=result.command, caption=caption)


# ------------------------------------------------------------------ #
# Code-post generation                                                 #
# ------------------------------------------------------------------ #


def generate_for_code_post(
    job_id: str,
    trace: ExecutionTrace,
    output_dir: Path,
) -> MediaManifest:
    """Generate the required screenshot pair for a code post.

    PRD §Screenshot Rule: 1 terminal + 1 output proof.

    Uses the first successful CommandResult for both screenshot types.
    If the trace is empty or all commands failed, items will be empty
    and validate_code_post_media() will report the gap.

    Args:
        job_id:     The BlogJob ID — embedded in the manifest.
        trace:      Execution trace from the Execution Layer.
        output_dir: Directory to write PNG files.

    Returns:
        MediaManifest with 0–2 items depending on trace content.
    """
    items: list[MediaItem] = []

    # Prefer the first successful result; fall back to the first result overall.
    primary = next(
        (r for r in trace.results if r.exit_code == 0),
        trace.results[0] if trace.results else None,
    )

    if primary is not None:
        items.append(capture_screenshot(primary, output_dir, MediaType.TERMINAL_SCREENSHOT))
        items.append(capture_screenshot(primary, output_dir, MediaType.OUTPUT_PROOF))

    return MediaManifest(job_id=job_id, items=items)


# ------------------------------------------------------------------ #
# Validation                                                           #
# ------------------------------------------------------------------ #


def validate_code_post_media(manifest: MediaManifest) -> list[str]:
    """Return a list of unmet media requirements for a code post.

    Empty list means the manifest satisfies PRD §Screenshot Rule.
    Non-empty list feeds directly into the review / revise loop as
    quality_gaps so the user knows what is missing.
    """
    gaps: list[str] = []
    if not manifest.has_terminal_screenshot:
        gaps.append(
            "Missing terminal screenshot — at least 1 required for code posts."
        )
    if not manifest.has_output_proof:
        gaps.append(
            "Missing output proof screenshot — at least 1 required for code posts."
        )
    return gaps
