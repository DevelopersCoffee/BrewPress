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
    draft.add_argument(
        "--auto-critic",
        action="store_true",
        help="Run the Critic Agent after generation and show the review inline.",
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

    # boost — Blog Boost Assistant: SEO audit, rewrite, feedback, topics, etc.
    boost = sub.add_parser(
        "boost",
        help="Run the Blog Boost Assistant (SEO audit, rewrite, feedback, topics, …).",
    )
    boost.add_argument(
        "task",
        metavar="TASK",
        choices=[
            "seo_audit",
            "rewrite",
            "title_suggestions",
            "meta_description",
            "content_feedback",
            "topic_ideas",
            "internal_linking",
            "engagement_message",
        ],
        help=(
            "Task to perform: seo_audit | rewrite | title_suggestions | "
            "meta_description | content_feedback | topic_ideas | "
            "internal_linking | engagement_message"
        ),
    )
    boost.add_argument(
        "--content",
        default="",
        metavar="TEXT_OR_PATH",
        help="Blog post content (inline text or path to a .md file).",
    )
    boost.add_argument(
        "--keywords",
        nargs="+",
        default=[],
        metavar="KW",
        help="Target keywords (e.g. --keywords 'spring boot' 'caching').",
    )
    boost.add_argument(
        "--audience",
        default="mid-to-senior backend developers",
        metavar="DESC",
        help="Target audience description.",
    )
    boost.add_argument(
        "--tone",
        default="professional, friendly, developer-focused",
        metavar="DESC",
        help="Desired writing tone.",
    )
    boost.add_argument(
        "--word-count",
        type=int,
        default=None,
        metavar="N",
        help="Target word count for rewrite tasks.",
    )
    boost.add_argument(
        "--format",
        choices=["blog", "email", "social"],
        default="blog",
        help="Output format for engagement_message tasks (default: blog).",
    )
    boost.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Emit the full BoostResult as JSON instead of human-readable output.",
    )
    boost.add_argument(
        "--from-draft",
        action="store_true",
        help="Load content from the current saved draft (~/.brewpress/last_draft.json).",
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

    # critic — LLM-based post review (Generator + Critic loop)
    critic_p = sub.add_parser(
        "critic",
        help="Run the Critic Agent to review the current draft and get a pass/revise verdict.",
    )
    critic_p.add_argument(
        "--apply",
        action="store_true",
        help="Apply the revision instruction automatically when verdict is 'revise'.",
    )
    critic_p.add_argument(
        "--eval",
        action="store_true",
        dest="run_eval",
        help="Also run deterministic quality checks (no API).",
    )

    # doctor — environment and connectivity check
    sub.add_parser("doctor", help="Check environment, credentials, and connectivity.")

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
    approve_publish.add_argument(
        "--attach",
        metavar="FILE",
        nargs="+",
        dest="attach_files",
        help="Attach local image/media files to the post (uploaded to WP media library).",
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
    reject.add_argument(
        "--force",
        action="store_true",
        help="Allow rejection even when job is in APPROVED_STEP_2 state.",
    )

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
                auto_approve=args.auto_approve,
                config=config,
            )
        except (ValueError, FileNotFoundError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        from brewpress.review_gate import format_draft
        print(format_draft(result.job))
        if result.pipeline_summary:
            print(result.pipeline_summary)
        if result.media_gaps:
            for gap in result.media_gaps:
                print(f"[brewpress] warning: {gap}", file=sys.stderr)

        if getattr(args, "auto_critic", False):
            print()
            rc = _run_critic_on_job(result.job, config, apply=False, run_eval=False)
            if rc != 0:
                return rc

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
        from pathlib import Path as _Path
        extra_media = [_Path(f) for f in (args.attach_files or [])]
        missing_files = [str(p) for p in extra_media if not p.is_file()]
        if missing_files:
            for f in missing_files:
                print(f"[brewpress] --attach: file not found: {f}", file=sys.stderr)
            return 1

        try:
            updated_job = Orchestrator().publish(config=config, extra_media_paths=extra_media)
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
            ReviewGate().reject(reason=args.reason, force=args.force)
            print("[brewpress] Draft rejected and discarded.")
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

    # ---------------------------------------------------------------- #
    # calibrate — fetch recent posts and build tone fingerprint         #
    # ---------------------------------------------------------------- #

    if args.command == "calibrate":
        import json as _json
        from pathlib import Path as _Path

        tone_path = _Path.home() / ".brewpress" / "tone.json"
        if tone_path.exists() and not args.force:
            print(
                f"[brewpress] Tone fingerprint already exists at {tone_path}. "
                "Use --force to recalibrate."
            )
            return 0

        from brewpress.config import load_config
        from brewpress.wp_client import WordPressClient
        try:
            config = load_config(required=("WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
        except OSError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

        try:
            client = WordPressClient(config)
            posts: list = client._get(
                "posts", per_page=20, status="publish", _fields="id,title,excerpt,slug,date"
            )
        except Exception as exc:
            print(f"[brewpress] Failed to fetch posts: {exc}", file=sys.stderr)
            return 1

        fingerprint = {
            "site_url": config.wp_url,
            "post_count": len(posts),
            "posts": [
                {
                    "id": p.get("id"),
                    "title": p.get("title", {}).get("rendered", ""),
                    "slug": p.get("slug", ""),
                    "date": p.get("date", ""),
                    "excerpt": p.get("excerpt", {}).get("rendered", ""),
                }
                for p in posts
            ],
        }

        tone_path.parent.mkdir(parents=True, exist_ok=True)
        tone_path.write_text(
            _json.dumps(fingerprint, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[brewpress] Tone fingerprint written to {tone_path} ({len(posts)} posts).")
        return 0

    # ---------------------------------------------------------------- #
    # suggest — surface topic ideas from trend signals                  #
    # ---------------------------------------------------------------- #

    if args.command == "suggest":
        from brewpress.trend_scout import NullTrendSource, TrendScout

        keywords: list[str] = args.topic or []
        scout = TrendScout(source=NullTrendSource(), region=args.region)
        suggestions = scout.suggest(keywords=keywords, limit=args.count)

        if not suggestions:
            print(
                "[brewpress] No suggestions generated. "
                "Connect a real TrendDataSource (e.g. Google Trends) to enable scoring."
            )
            if keywords:
                print("[brewpress] Evaluated keywords: " + ", ".join(keywords))
            return 0

        for i, s in enumerate(suggestions, start=1):
            print(f"{i}. {s.topic} [{s.strategy}] score={s.score:.2f}")
            print(f"   Angle:    {s.angle}")
            print(f"   Keywords: {', '.join(s.keywords)}")
            print(f"   Why:      {s.reasoning}")
            print()
        return 0

    if args.command == "doctor":
        return _run_doctor()

    if args.command == "critic":
        from brewpress.config import load_config
        from brewpress.review_gate import ReviewGate
        try:
            config = load_config(required=("GOOGLE_API_KEY",))
            job = ReviewGate().review()
        except (OSError, FileNotFoundError) as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
        return _run_critic_on_job(
            job, config,
            apply=args.apply,
            run_eval=args.run_eval,
        )

    if args.command == "boost":
        return _run_boost(args)

    print(f"[brewpress] '{args.command}' is not yet implemented.")
    return 0


def _run_critic_on_job(
    job: object,
    config: object,
    apply: bool,
    run_eval: bool,
) -> int:
    """Run the CriticAgent on a BlogJob and display results.

    Args:
        job:      BlogJob to review.
        config:   BrewPressConfig with GOOGLE_API_KEY.
        apply:    When True and verdict is "revise", call ReviewGate.revise().
        run_eval: When True, also run deterministic boost_eval checks.
    """
    from brewpress.critic_agent import CriticAgent

    try:
        critic = CriticAgent(config)  # type: ignore[arg-type]
        result = critic.review(job)  # type: ignore[arg-type]
    except (ValueError, RuntimeError) as exc:
        print(f"[brewpress] Critic failed: {exc}", file=sys.stderr)
        return 1

    print("── Critic Review ───────────────────────────────────────────")
    print(f"  Verdict:  {result.verdict.upper()}")
    print(
        f"  Scores:   SEO={result.scores.seo_quality}  "
        f"Clarity={result.scores.clarity}  "
        f"TechAccuracy={result.scores.technical_accuracy}  "
        f"PublishReady={result.scores.publish_readiness}"
    )
    if result.failures:
        print("  Issues:")
        for issue in result.failures:
            print(f"    • {issue}")
    if result.revision_instruction:
        print(f"  Fix:      {result.revision_instruction}")
    print()

    if run_eval:
        from brewpress.boost_eval import run_checks
        eval_result = run_checks(job)  # type: ignore[arg-type]
        print("── Deterministic Checks ────────────────────────────────────")
        print(eval_result)
        print()

    if not result.is_pass() and apply:
        from brewpress.review_gate import ReviewGate
        try:
            ReviewGate().revise(result.revision_instruction)
            print(
                "[brewpress] Revision instruction applied. "
                "Run 'brewpress draft' (with same args) to regenerate."
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"[brewpress] Could not apply revision: {exc}", file=sys.stderr)
            return 1

    return 0


def _run_boost(args: argparse.Namespace) -> int:  # noqa: PLR0912
    """Run the Blog Boost Assistant for the requested task."""
    import json as _json
    import os

    from brewpress.blog_boost import BlogBoostAgent, BoostRequest
    from brewpress.config import load_config

    # Resolve content: --from-draft, --content PATH, or inline --content TEXT
    content = args.content or ""
    if args.from_draft:
        from brewpress.state_store import StateStore
        try:
            job = StateStore().load()
            content = job.draft_body_md or ""
        except FileNotFoundError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1
    elif content and os.path.isfile(content):
        try:
            from pathlib import Path
            content = Path(content).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[brewpress] Cannot read file: {exc}", file=sys.stderr)
            return 1

    # Load config (only needs GOOGLE_API_KEY)
    try:
        config = load_config(required=("GOOGLE_API_KEY",))
    except OSError as exc:
        print(f"[brewpress] {exc}", file=sys.stderr)
        return 1

    request = BoostRequest(
        task_type=args.task,
        content=content,
        keywords=args.keywords,
        target_audience=args.audience,
        tone=args.tone,
        word_count=args.word_count,
        format=args.format,
    )

    try:
        agent = BlogBoostAgent(config)
        result = agent.run(request)
    except (ValueError, RuntimeError) as exc:
        print(f"[brewpress] Boost failed: {exc}", file=sys.stderr)
        return 1

    if args.output_json:
        print(_json.dumps(result.to_json(), indent=2, ensure_ascii=False))
        return 0

    # Human-readable output
    if result.optimized_content:
        print(result.optimized_content)
        print()

    seo = result.seo_suggestions
    if any([seo.keywords_used, seo.missing_keywords, seo.title_feedback,
            seo.meta_description, seo.readability_score]):
        print("── SEO ─────────────────────────────────────────────────────")
        if seo.title_feedback:
            print(f"Title:       {seo.title_feedback}")
        if seo.meta_description:
            print(f"Meta:        {seo.meta_description}")
        if seo.readability_score:
            print(f"Readability: {seo.readability_score}")
        if seo.keywords_used:
            print(f"Keywords ✓:  {', '.join(seo.keywords_used)}")
        if seo.missing_keywords:
            print(f"Keywords ✗:  {', '.join(seo.missing_keywords)}")
        print()

    if result.structure_improvements:
        print("── Structure ───────────────────────────────────────────────")
        for item in result.structure_improvements:
            print(f"  • {item}")
        print()

    if result.engagement_tips:
        print("── Engagement ──────────────────────────────────────────────")
        for tip in result.engagement_tips:
            print(f"  • {tip}")
        print()

    return 0


def _run_doctor() -> int:
    """Check environment, credentials, and connectivity. Returns 0 if all checks pass."""
    import os
    import sys as _sys

    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        icon = "OK" if passed else "FAIL"
        msg = f"  [{icon}] {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        if not passed:
            ok = False

    print("BrewPress doctor\n")

    # Python version
    major, minor = _sys.version_info[:2]
    check(f"Python {major}.{minor}", major == 3 and minor >= 11,
          "requires Python 3.11+" if not (major == 3 and minor >= 11) else "")

    # Env vars
    env_vars = {
        "WP_URL": os.environ.get("WP_URL", "").strip(),
        "WP_USERNAME": os.environ.get("WP_USERNAME", "").strip(),
        "WP_APP_PASSWORD": os.environ.get("WP_APP_PASSWORD", "").strip(),
        "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", "").strip(),
    }
    for name, value in env_vars.items():
        check(f"env {name}", bool(value), "not set" if not value else "")

    # HTTPS enforcement
    wp_url = env_vars["WP_URL"]
    if wp_url:
        check("WP_URL uses HTTPS", wp_url.startswith("https://"),
              "must start with https://" if not wp_url.startswith("https://") else "")

    # WordPress connectivity
    if env_vars["WP_URL"] and env_vars["WP_USERNAME"] and env_vars["WP_APP_PASSWORD"]:
        from brewpress.config import BrewPressConfig
        from brewpress.wp_client import WordPressClient
        try:
            cfg = BrewPressConfig(
                wp_url=wp_url.rstrip("/"),
                wp_username=env_vars["WP_USERNAME"],
                wp_app_password=env_vars["WP_APP_PASSWORD"],
            )
            client = WordPressClient(cfg)
            posts = client._get("posts", per_page=1, _fields="id")
            check("WordPress connectivity", True, f"reachable ({len(posts)} post sampled)")
        except Exception as exc:
            check("WordPress connectivity", False, str(exc)[:120])
    else:
        print("  [SKIP] WordPress connectivity — credentials incomplete")

    # Gemini availability (basic import check)
    if env_vars["GOOGLE_API_KEY"]:
        try:
            from google import genai as _genai  # noqa: F401
            check("google-genai package", True)
        except ImportError:
            check("google-genai package", False, "run: pip install google-genai")
    else:
        print("  [SKIP] google-genai check — GOOGLE_API_KEY not set")

    # Tone fingerprint
    from pathlib import Path as _Path
    tone_path = _Path.home() / ".brewpress" / "tone.json"
    if tone_path.exists():
        print(f"  [OK]   tone fingerprint — {tone_path}")
    else:
        print(f"  [INFO] tone fingerprint not found at {tone_path} (run brewpress calibrate)")

    print()
    if ok:
        print("All checks passed.")
        return 0
    else:
        print("Some checks failed. Fix the issues above and re-run brewpress doctor.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
