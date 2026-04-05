"""Orchestrator — end-to-end pipeline wiring for BrewPress MVP.

Connects every agent and module into two callable pipelines:

    draft()    ingest → DraftAgent → ExecutionLayer → MediaAgent → StateStore
    publish()  StateStore → WordPressClient → StateStore (or failure bundle)

All dependencies are injected at construction time, which keeps each
pipeline fully testable without real API keys or a live WordPress instance.

The two pipelines map directly to the CLI commands:

    brewpress draft ...          → Orchestrator.draft()
    brewpress approve-publish    → Orchestrator.publish()

Determinism guarantee:
    State transitions are 1-to-1 with the BlogJob state machine.
    No AI calls happen outside draft().
    No WP network calls happen outside publish().
    No command runs without the user having provided it via notes or diff.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from brewpress.config import BrewPressConfig
from brewpress.draft_agent import DraftAgent
from brewpress.execution_layer import run_commands
from brewpress.media_agent import generate_for_code_post, validate_code_post_media
from brewpress.models import BlogJob
from brewpress.review_gate import ReviewGate
from brewpress.state_store import StateStore
from brewpress.work_ingestion import WorkContext, ingest
from brewpress.wordpress.agent import WordPressAgent
from brewpress.wp_client import (
    AmbiguousMatchError,
    PublishError,
    WordPressClient,
    generate_failure_bundle,
)

# Default media output directory — one subdirectory per job_id.
_DEFAULT_MEDIA_BASE = Path.home() / ".brewpress" / "media"


# ------------------------------------------------------------------ #
# Result type                                                          #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class DraftResult:
    """Outcome of the draft pipeline."""

    job: BlogJob
    media_gaps: list[str]  # empty = all media requirements met


# ------------------------------------------------------------------ #
# Orchestrator                                                         #
# ------------------------------------------------------------------ #


class Orchestrator:
    """Wire all agents together for the BrewPress MVP pipeline.

    Args:
        store:        StateStore for job persistence.
        draft_agent:  Pre-built DraftAgent.  When None, one is constructed
                      from the ``config`` passed to draft().
        wp_client:    Pre-built WordPressClient.  When None, one is
                      constructed from the ``config`` passed to publish().
        media_base:   Base directory for media output.  Defaults to
                      ~/.brewpress/media/.
    """

    def __init__(
        self,
        store: StateStore | None = None,
        draft_agent: DraftAgent | None = None,
        wp_client: WordPressClient | None = None,
        wp_agent: WordPressAgent | None = None,
        media_base: Path | None = None,
    ) -> None:
        self._store = store or StateStore()
        self._draft_agent = draft_agent
        self._wp_client = wp_client
        self._wp_agent = wp_agent
        self._media_base = media_base or _DEFAULT_MEDIA_BASE

    # ---------------------------------------------------------------- #
    # Draft pipeline                                                     #
    # ---------------------------------------------------------------- #

    def draft(
        self,
        topic: str,
        notes: str = "",
        diff_path: str | None = None,
        pr_url: str | None = None,
        force: bool = False,
        auto_approve: bool = False,
        config: BrewPressConfig | None = None,
    ) -> DraftResult:
        """Run the full draft generation pipeline.

        Steps:
            1. Normalize inputs into a WorkContext (Stack 3).
            2. Generate a structured BlogJob via DraftAgent (Stack 4).
            3. Run extracted shell commands via ExecutionLayer (Stack 7).
            4. Capture terminal + output proof screenshots (Stack 7).
            5. Save the job and transition to REVIEWED so the user can
               immediately run approve-content.

        Args:
            topic:     Blog topic or angle (required when diff_path is None).
            notes:     Work notes or additional context.
            diff_path: Path to a local git diff file.
            pr_url:    GitHub PR URL (stored, not fetched in MVP).
            force:     Bypass is_single_topic check and missing-media warning.
            config:    BrewPressConfig with GOOGLE_API_KEY.  Required when
                       draft_agent was not injected.

        Returns:
            DraftResult with the REVIEWED job and any media gap strings.
            Gap strings are warnings, not hard failures (unless force=False
            and the job is a code post without any runnable commands).

        Raises:
            ValueError: draft_agent not injected and config not provided.
            ValueError: DraftAgent.generate() raises (model error or
                        multi-topic guard without force=True).
            FileNotFoundError: diff_path provided but file does not exist.
        """
        ctx = ingest(topic, notes, diff_path, pr_url)

        agent = self._draft_agent
        if agent is None:
            if config is None:
                raise ValueError(
                    "Orchestrator.draft() requires either an injected draft_agent "
                    "or a BrewPressConfig with GOOGLE_API_KEY."
                )
            agent = DraftAgent(config)

        job = agent.generate(ctx, force=force)

        media_gaps: list[str] = []
        media_output_dir = self._media_base / job.job_id

        if ctx.is_code_post and ctx.commands:
            trace = run_commands(ctx.commands, job_id=job.job_id)
            manifest = generate_for_code_post(job.job_id, trace, media_output_dir)
            media_gaps = validate_code_post_media(manifest)

        elif ctx.is_code_post and not ctx.commands:
            # Code post detected (diff or PR URL present) but no $ commands
            # in the notes/diff.  Screenshots cannot be auto-generated.
            media_gaps = [
                "Code post with no runnable commands — "
                "add '$ <command>' lines to your notes to enable "
                "terminal and output proof screenshot capture."
            ]

        # Tag the job with content-type for downstream use (publish, linking).
        job = job.model_copy(update={"is_code_post": ctx.is_code_post})

        # Save in DRAFT state, then immediately transition to REVIEWED.
        # The user sees the draft on the same invocation and can run
        # approve-content without a separate `brewpress review` call.
        self._store.save(job)
        gate = ReviewGate(store=self._store)
        reviewed_job = gate.review()

        # --auto-approve: immediately approve content after review so the user
        # can go straight to approve-publish without a separate command.
        if auto_approve:
            reviewed_job = gate.approve_content()

        return DraftResult(job=reviewed_job, media_gaps=media_gaps)

    # ---------------------------------------------------------------- #
    # Publish pipeline                                                   #
    # ---------------------------------------------------------------- #

    def publish(
        self,
        config: BrewPressConfig | None = None,
        bundle_dir: Path | None = None,
    ) -> BlogJob:
        """Publish the APPROVED_STEP_2 job to WordPress.

        Reads the active job, verifies its state, calls the WP REST API,
        persists the returned wp_post_id, and returns the updated job.

        On PublishError the failure bundle is written to bundle_dir
        (defaults to ~/.brewpress/bundles/) before re-raising so the caller
        can tell the user where to find it.

        Args:
            config:     BrewPressConfig with WP credentials.  Required when
                        wp_client was not injected.
            bundle_dir: Directory for the failure bundle JSON file.

        Returns:
            Updated BlogJob with wp_post_id set.

        Raises:
            FileNotFoundError:   No draft exists in StateStore.
            ValueError:          Job is not in APPROVED_STEP_2 state, OR
                                 wp_client not injected and config not provided.
            AmbiguousMatchError: Multiple WP posts match — caller must set
                                 target_wp_post_id and retry.
            PublishError:        WP API call failed; bundle written to bundle_dir.
        """
        job = self._store.load()

        if job.state.value != "approved_step_2":
            raise ValueError(
                f"publish() requires state approved_step_2, got {job.state.value!r}. "
                "Run 'brewpress approve-content' then 'brewpress approve-publish' first."
            )

        client = self._wp_client
        if client is None:
            if config is None:
                raise ValueError(
                    "Orchestrator.publish() requires either an injected wp_client "
                    "or a BrewPressConfig with WP credentials."
                )
            client = WordPressClient(config)

        _bundle_dir = bundle_dir or (Path.home() / ".brewpress" / "bundles")

        # Upload featured image for code posts when screenshots are available.
        # Uses the terminal screenshot (most legible) as the post hero image.
        featured_media_id: int | None = None
        if job.is_code_post:
            media_dir = self._media_base / job.job_id
            screenshots = sorted(media_dir.glob("terminal_*.png")) if media_dir.is_dir() else []
            if screenshots:
                try:
                    featured_media_id = client.upload_image_file(screenshots[0])
                except PublishError:
                    pass  # media upload failure is non-fatal; post continues without hero

        try:
            updated_job = client.publish(job, featured_media_id=featured_media_id)
        except PublishError:
            _bundle_dir.mkdir(parents=True, exist_ok=True)
            bundle_path = _bundle_dir / f"failure_bundle_{job.job_id[:8]}.json"
            generate_failure_bundle(job, path=bundle_path)
            raise

        self._store.save(updated_job)
        return updated_job
