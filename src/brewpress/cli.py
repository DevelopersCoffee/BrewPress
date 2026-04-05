"""BrewPress CLI entrypoint.

Subcommands are registered here. Business logic lives in agent modules.
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

    # suggest — surface topic and keyword ideas from trend signals
    suggest = sub.add_parser(
        "suggest",
        help="Suggest blog topics and keywords using trend signals.",
    )
    suggest.add_argument(
        "--topic",
        metavar="KEYWORD",
        nargs="+",
        help="Seed keywords to evaluate (e.g. 'spring boot' 'ai agents').",
    )
    suggest.add_argument(
        "--region",
        default="US",
        metavar="CC",
        help="ISO 3166-1 alpha-2 region code (default: US).",
    )
    suggest.add_argument(
        "--count",
        type=int,
        default=5,
        metavar="N",
        help="Maximum number of suggestions to return (default: 5).",
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

    # revise — apply a revision instruction (resets approvals per PRD rules)
    revise = sub.add_parser(
        "revise",
        help="Apply a revision instruction and reset approvals as needed.",
    )
    revise.add_argument(
        "instruction",
        help="Revision instruction (e.g. 'shorten the introduction').",
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
        from brewpress.config import load_config
        from brewpress.orchestrator import Orchestrator
        try:
            config = load_config(required=("GOOGLE_API_KEY",))
        except OSError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        try:
            result = Orchestrator().draft(
                topic=args.topic,
                notes=args.notes,
                diff_path=args.diff_path,
                pr_url=args.pr_url,
                force=args.force,
                config=config,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        from brewpress.review_gate import format_draft
        print(format_draft(result.job))
        if result.media_gaps:
            for gap in result.media_gaps:
                print(f"[brewpress] warning: {gap}", file=sys.stderr)
        return 0

    # ---------------------------------------------------------------- #
    # Review-loop commands — wired to ReviewGate                        #
    # ---------------------------------------------------------------- #

    if args.command == "review":
        from brewpress.review_gate import ReviewGate, format_draft
        try:
            job = ReviewGate().review()
            print(format_draft(job))
            return 0
        except FileNotFoundError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

    if args.command == "revise":
        from brewpress.review_gate import ReviewGate
        try:
            ReviewGate().revise(args.instruction)
            print(
                "[brewpress] Revision recorded. "
                "Run 'brewpress draft' to regenerate with this instruction."
            )
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

    if args.command == "approve-content":
        from brewpress.review_gate import ReviewGate
        try:
            ReviewGate().approve_content()
            print(
                "[brewpress] Content approved (step 1 of 2). "
                "Run 'brewpress approve-publish' to queue for WordPress."
            )
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

    if args.command == "approve-publish":
        from brewpress.config import load_config
        from brewpress.orchestrator import Orchestrator
        from brewpress.review_gate import ReviewGate
        from brewpress.wp_client import AmbiguousMatchError, PublishError
        # Load WP credentials before transitioning state so a missing
        # env var cannot leave the job stuck in APPROVED_STEP_2 with no
        # publish having happened.
        try:
            config = load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
        except OSError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        # Transition state to APPROVED_STEP_2 only after credentials are confirmed.
        try:
            ReviewGate().approve_publish(live=args.live)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        try:
            updated_job = Orchestrator().publish(config=config)
        except AmbiguousMatchError as exc:
            print(f"[brewpress] Ambiguous WP post match: {exc}", file=sys.stderr)
            return 1
        except PublishError as exc:
            from pathlib import Path
            bundle_dir = Path.home() / ".brewpress" / "bundles"
            print(f"[brewpress] WordPress publish failed: {exc}", file=sys.stderr)
            print(f"[brewpress] Failure bundle written to {bundle_dir}/", file=sys.stderr)
            try:
                ReviewGate().rollback_publish_approval()
                print(
                    "[brewpress] State rolled back to approved_step_1. "
                    "Run 'brewpress approve-publish' to retry.",
                    file=sys.stderr,
                )
            except (FileNotFoundError, ValueError):
                pass
            return 1
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        dest = "live" if updated_job.publish_live else "draft"
        print(f"[brewpress] Published to WordPress as {dest}. Post ID: {updated_job.wp_post_id}")
        return 0

    if args.command == "reject":
        from brewpress.review_gate import ReviewGate
        try:
            ReviewGate().reject(reason=args.reason)
            print("[brewpress] Draft rejected and discarded.")
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

    # ---------------------------------------------------------------- #
    # Remaining stubs — implementation arrives in later stacks          #
    # ---------------------------------------------------------------- #
    print(f"[brewpress] '{args.command}' is not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
