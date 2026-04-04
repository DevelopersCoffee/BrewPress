"""BrewPress CLI entrypoint.

Subcommands are registered here. Business logic lives in agent modules.
All subcommands below are stubs — implementation arrives in later stacks.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brewpress",
        description="ADK-powered blog generation and WordPress publishing.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the current BrewPress version and exit.",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # draft — generate a new blog post from a diff and/or topic
    draft = sub.add_parser("draft", help="Generate a new blog post draft.")
    draft.add_argument(
        "--diff",
        dest="diff_path",
        metavar="PATH",
        help="Path to a local git diff file. Provides code grounding for generation.",
    )
    draft.add_argument(
        "--topic",
        default="",
        help="Blog post topic or angle (optional when --diff is provided).",
    )
    draft.add_argument("--notes", default="", help="Work notes or additional context.")
    draft.add_argument(
        "--pr-url", metavar="URL", help="GitHub PR URL to use as grounding (Phase 2)."
    )
    draft.add_argument(
        "--files",
        metavar="PATH",
        nargs="+",
        help="Narrow diff scope to specific file paths.",
    )
    draft.add_argument(
        "--force",
        action="store_true",
        help="Generate even if is_single_topic check fails.",
    )
    draft.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the interactive [y/N] content approval prompt.",
    )

    # calibrate — fetch recent posts and build a tone fingerprint
    calibrate = sub.add_parser(
        "calibrate",
        help="Fetch recent posts and calibrate tone fingerprint (~/.brewpress/tone.json).",
    )
    calibrate.add_argument(
        "--force",
        action="store_true",
        help="Re-calibrate even if tone.json already exists.",
    )

    # review — display the current draft
    sub.add_parser("review", help="Display the current draft for review.")

    # approve-content — mark content approved (step 1 of 2)
    sub.add_parser("approve-content", help="Approve the content (step 1 of 2).")

    # approve-publish — send to WordPress (step 2 of 2)
    approve_publish = sub.add_parser(
        "approve-publish",
        help="Approve and send to WordPress (step 2 of 2). Default: draft.",
    )
    approve_publish.add_argument(
        "--live",
        action="store_true",
        help="Publish live instead of saving as draft. Never inferred implicitly.",
    )

    # reject — terminate the current job
    reject = sub.add_parser("reject", help="Reject and discard the current draft.")
    reject.add_argument("--reason", default="", help="Optional rejection reason.")

    return parser


def _validate_draft_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Require at least --diff or --topic for the draft subcommand."""
    if not args.diff_path and not args.topic:
        parser.error("draft requires at least one of --diff or --topic.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        from brewpress import __version__
        print(__version__)
        return 0

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "draft":
        _validate_draft_args(args, parser)

    # Subcommand stubs — each will delegate to an agent in a later stack.
    print(f"[brewpress] '{args.command}' is not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
