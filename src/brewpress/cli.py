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

    # draft — create a new blog post job
    draft = sub.add_parser("draft", help="Create a new blog post draft.")
    draft.add_argument("--topic", required=True, help="Blog post topic.")
    draft.add_argument("--notes", default="", help="Work notes or context.")
    draft.add_argument("--diff", dest="diff_path", metavar="PATH", help="Path to a local git diff file.")
    draft.add_argument("--pr-url", metavar="URL", help="GitHub PR URL to use as grounding.")

    # review — show the current draft for review
    sub.add_parser("review", help="Display the current draft for review.")

    # approve-content — mark content approved (step 1 of 2)
    sub.add_parser("approve-content", help="Approve the content (step 1 of 2).")

    # approve-publish — send to WordPress; --live publishes immediately
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

    # Subcommand stubs — each will delegate to an agent in a later stack.
    print(f"[brewpress] '{args.command}' is not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
