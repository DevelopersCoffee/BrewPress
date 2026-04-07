"""Orchestrator — end-to-end pipeline wiring for BrewPress GA.

Connects every agent and module into two callable pipelines:

    draft()    ingest → WriterAgent → StructurerAgent → SEOAgent → CriticAgent (loop)
               → ExecutionLayer → MediaAgent → StateStore
    publish()  StateStore → WordPressClient → StateStore (or failure bundle)

All dependencies are injected at construction time, which keeps each
pipeline fully testable without real API keys or a live WordPress instance.

The two pipelines map directly to the CLI commands:

    brewpress draft ...          → Orchestrator.draft()
    brewpress approve-publish    → Orchestrator.publish()

Revision loop:
    CriticAgent returns verdict "pass" or "revise".
    On "revise", all 4 agents re-run with the revision_instruction injected into
    WriterAgent.  Maximum MAX_REVISIONS=3 iterations.  If the critic has not passed
    after 3 iterations, the job is rejected with reason "max_revisions_exceeded".

Determinism guarantee:
    State transitions are 1-to-1 with the BlogJob state machine.
    No AI calls happen outside draft().
    No WP network calls happen outside publish().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from brewpress.config import BrewPressConfig
from brewpress.execution_layer import run_commands
from brewpress.media_agent import generate_for_code_post, validate_code_post_media
from brewpress.models import BlogJob
from brewpress.review_gate import ReviewGate
from brewpress.state_store import StateStore
from brewpress.wordpress.agent import WordPressAgent
from brewpress.work_ingestion import ingest
from brewpress.wp_client import (
    PublishError,
    WordPressClient,
    generate_failure_bundle,
)

if TYPE_CHECKING:
    from brewpress.writer_agent import WriterAgent
    from brewpress.structurer_agent import StructurerAgent
    from brewpress.seo_agent import SEOAgent
    from brewpress.critic_agent import CriticAgent

MAX_REVISIONS: int = 3

# Default media output directory — one subdirectory per job_id.
_DEFAULT_MEDIA_BASE = Path.home() / ".brewpress" / "media"


# ------------------------------------------------------------------ #
# Pipeline bundle                                                       #
# ------------------------------------------------------------------ #


@dataclass
class PipelineAgents:
    """Bundle of the 4 draft-pipeline agents.

    Pass to Orchestrator.__init__ for dependency injection (testing, etc.).
    When None is passed to Orchestrator, agents are built from config at
    draft() call time.
    """

    writer: "WriterAgent | None" = field(default=None)
    structurer: "StructurerAgent | None" = field(default=None)
    seo: "SEOAgent | None" = field(default=None)
    critic: "CriticAgent | None" = field(default=None)


# ------------------------------------------------------------------ #
# Result type                                                          #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class DraftResult:
    """Outcome of the draft pipeline."""

    job: BlogJob
    media_gaps: list[str]  # empty = all media requirements met
    pipeline_summary: str = ""  # CLI-3: "[pipeline] N rounds | seo: 5, ..."


# ------------------------------------------------------------------ #
# Orchestrator                                                         #
# ------------------------------------------------------------------ #


class Orchestrator:
    """Wire all agents together for the BrewPress GA pipeline.

    Args:
        store:     StateStore for job persistence.
        pipeline:  Pre-built PipelineAgents.  When None, agents are
                   constructed from the config passed to draft().
        wp_client: Pre-built WordPressClient.
        media_base: Base directory for media output.
    """

    def __init__(
        self,
        store: StateStore | None = None,
        pipeline: PipelineAgents | None = None,
        wp_client: WordPressClient | None = None,
        wp_agent: WordPressAgent | None = None,
        media_base: Path | None = None,
    ) -> None:
        self._store = store or StateStore()
        self._pipeline = pipeline
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
            1. Normalize inputs into a WorkContext.
            2. Run 4-agent pipeline: Writer → Structurer → SEO → Critic (loop).
            3. On critic "revise": store revision_instruction, increment
               revision_attempt, re-run all 4 agents.  Max MAX_REVISIONS times.
            4. On max revisions exceeded: reject the job.
            5. Run ExecutionLayer + MediaAgent for code posts.
            6. Transition to REVIEWED and optionally auto-approve.

        Returns:
            DraftResult with the REVIEWED (or APPROVED_STEP_1) job,
            media_gaps list, and pipeline_summary string.

        Raises:
            ValueError: Neither pipeline nor config provided.
            ValueError: WriterAgent flagged multi-topic and force=False.
            FileNotFoundError: diff_path provided but file does not exist.
        """
        ctx = ingest(topic, notes, diff_path, pr_url)
        agents = self._resolve_pipeline(config)

        # ---- 4-agent revision loop ---------------------------------- #
        job = BlogJob()
        pipeline_summary = ""

        for attempt in range(MAX_REVISIONS):
            if attempt == 0:
                job = agents.writer.generate(ctx, force=force)
            else:
                job = agents.writer.generate_revision(job, ctx)

            job = agents.structurer.structure(job)
            job = agents.seo.optimize(job)
            critic_result = agents.critic.review(job)

            if critic_result.is_pass():
                scores = critic_result.scores
                rounds = attempt + 1
                pipeline_summary = (
                    f"[pipeline] {rounds} round{'s' if rounds > 1 else ''} | "
                    f"seo: {scores.seo_quality}, clarity: {scores.clarity}, "
                    f"tech_accuracy: {scores.technical_accuracy}, "
                    f"readiness: {scores.publish_readiness}"
                )
                break

            # Critic said revise — store instruction and loop
            job = job.model_copy(update={
                "revise_instruction": critic_result.revision_instruction,
                "revision_attempt": attempt + 1,
            })
        else:
            # Exhausted all attempts without a pass
            rejected = job.reject(reason="max_revisions_exceeded")
            self._store.save(rejected)
            return DraftResult(job=rejected, media_gaps=[], pipeline_summary="")

        # ---- ExecutionLayer + MediaAgent (code posts) --------------- #
        media_gaps: list[str] = []
        media_output_dir = self._media_base / job.job_id

        if ctx.is_code_post and ctx.commands:
            trace = run_commands(ctx.commands, job_id=job.job_id)
            manifest = generate_for_code_post(job.job_id, trace, media_output_dir)
            media_gaps = validate_code_post_media(manifest)
        elif ctx.is_code_post and not ctx.commands:
            media_gaps = [
                "Code post with no runnable commands — "
                "add '$ <command>' lines to your notes to enable "
                "terminal and output proof screenshot capture."
            ]

        job = job.model_copy(update={"is_code_post": ctx.is_code_post})

        # ---- Transition to REVIEWED --------------------------------- #
        self._store.save(job)
        gate = ReviewGate(store=self._store)
        reviewed_job = gate.review()

        if auto_approve:
            reviewed_job = gate.approve_content()

        return DraftResult(
            job=reviewed_job,
            media_gaps=media_gaps,
            pipeline_summary=pipeline_summary,
        )

    def _resolve_pipeline(self, config: BrewPressConfig | None) -> PipelineAgents:
        """Return injected pipeline or build all 4 agents from config."""
        if self._pipeline is not None:
            p = self._pipeline
            missing = [
                name for name, agent in [
                    ("writer", p.writer), ("structurer", p.structurer),
                    ("seo", p.seo), ("critic", p.critic),
                ]
                if agent is None
            ]
            if missing:
                raise ValueError(
                    f"PipelineAgents is missing: {', '.join(missing)}. "
                    "Either inject all 4 agents or pass config= to build them."
                )
            return self._pipeline

        if config is None:
            raise ValueError(
                "Orchestrator.draft() requires either an injected PipelineAgents "
                "or a BrewPressConfig with GOOGLE_API_KEY."
            )

        from brewpress.writer_agent import WriterAgent
        from brewpress.structurer_agent import StructurerAgent
        from brewpress.seo_agent import SEOAgent
        from brewpress.critic_agent import CriticAgent

        return PipelineAgents(
            writer=WriterAgent(config),
            structurer=StructurerAgent(config),
            seo=SEOAgent(config),
            critic=CriticAgent(config),
        )

    # ---------------------------------------------------------------- #
    # Publish pipeline                                                   #
    # ---------------------------------------------------------------- #

    def publish(
        self,
        config: BrewPressConfig | None = None,
        bundle_dir: Path | None = None,
        extra_media_paths: list[Path] | None = None,
    ) -> BlogJob:
        """Publish the APPROVED_STEP_2 job to WordPress.

        Reads the active job, verifies its state, calls the WP REST API,
        persists the returned wp_post_id, and returns the updated job.

        On PublishError the failure bundle is written to bundle_dir
        (defaults to ~/.brewpress/bundles/) before re-raising.

        Args:
            config:     BrewPressConfig with WP credentials.
            bundle_dir: Directory for the failure bundle JSON file.

        Returns:
            Updated BlogJob with wp_post_id set.

        Raises:
            FileNotFoundError:   No draft exists in StateStore.
            ValueError:          Job is not in APPROVED_STEP_2 state, OR
                                 wp_client not injected and config not provided.
            AmbiguousMatchError: Multiple WP posts match.
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

        from brewpress.wp_client import UploadedMedia

        featured_media_id: int | None = None
        if job.is_code_post:
            media_dir = self._media_base / job.job_id
            screenshots = sorted(media_dir.glob("terminal_*.png")) if media_dir.is_dir() else []
            if screenshots:
                try:
                    hero = client.upload_image_file(screenshots[0])
                    featured_media_id = hero.id
                except PublishError:
                    pass

        gallery_media: list[UploadedMedia] = []
        for media_path in (extra_media_paths or []):
            if media_path.is_file():
                try:
                    gallery_media.append(client.upload_image_file(media_path))
                except PublishError:
                    pass

        try:
            updated_job = client.publish(
                job,
                featured_media_id=featured_media_id,
                gallery_media=gallery_media or None,
            )
        except PublishError:
            _bundle_dir.mkdir(parents=True, exist_ok=True)
            bundle_path = _bundle_dir / f"failure_bundle_{job.job_id[:8]}.json"
            generate_failure_bundle(job, path=bundle_path)
            raise

        self._store.save(updated_job)
        return updated_job
