"""Review Gate — deterministic review loop for the active BlogJob.

Sits between the CLI and the BlogJob state machine. Loads the active job
from StateStore, applies the requested command, saves the result, and
returns the updated job.

Command surface (PRD §Review Commands):
    review              Load draft; transition DRAFT → REVIEWED.
    revise <instr>      Store instruction; reset approvals per PRD rules.
    approve_content     REVIEWED → APPROVED_STEP_1 (step 1 of 2).
    approve_publish     APPROVED_STEP_1 → APPROVED_STEP_2 (WP draft, step 2 of 2).
    approve_publish live=True  Same, but flag for live publish.
    reject              Any non-terminal → REJECTED.

Invariants:
    - Live publish is never inferred — only set when live=True is explicit.
    - Approval states cannot be skipped; the state machine raises on violations.
    - Every command is deterministic: no AI calls, no network I/O, no randomness.
    - Every state change is persisted before returning.

ADK integration note: ReviewGate methods map cleanly to ADK Tool calls
once the full pipeline is wired. StateStore provides the session context.
"""

from __future__ import annotations

from brewpress.models import BlogJob, JobState
from brewpress.state_store import StateStore

# ------------------------------------------------------------------ #
# Display formatting                                                   #
# ------------------------------------------------------------------ #

_RULE = "-" * 60


def format_draft(job: BlogJob) -> str:
    """Format a BlogJob for terminal display during the review loop.

    Pure function — no I/O.  Suitable for piping or capture in tests.
    """
    lines: list[str] = []

    lines.append(_RULE)
    lines.append(f"State:   {job.state.value}")
    if job.quality_score is not None:
        lines.append(f"Quality: {job.quality_score}/100")
        if job.quality_gaps:
            for gap in job.quality_gaps:
                lines.append(f"         ! {gap}")

    lines.append(_RULE)
    lines.append(f"Title:   {job.title}")
    lines.append(f"Slug:    {job.slug}")
    lines.append(f"Meta:    {job.meta_description}")
    body_preview = (
        f"{job.draft_body_md[:120].strip()}..."
        if len(job.draft_body_md) > 120
        else job.draft_body_md.strip()
    )
    lines.append(f"Excerpt: {body_preview}")

    secondary = ", ".join(job.secondary_keywords) if job.secondary_keywords else "—"
    lines.append(f"Keywords: {job.primary_keyword}  |  {secondary}")

    if job.outline:
        lines.append("")
        lines.append("Outline:")
        for i, heading in enumerate(job.outline, start=1):
            lines.append(f"  {i}. {heading}")

    if job.draft_body_md:
        lines.append("")
        lines.append(_RULE)
        lines.append("Draft body:")
        lines.append("")
        lines.append(job.draft_body_md)

    lines.append(_RULE)

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# ReviewGate                                                           #
# ------------------------------------------------------------------ #


class ReviewGate:
    """Apply review commands to the active BlogJob.

    Args:
        store: StateStore instance. Defaults to the default path
               (~/.brewpress/last_draft.json).

    All public methods follow the same contract:
        1. Load the active job from the store.
        2. Apply the state transition.
        3. Persist the updated job.
        4. Return the updated job.

    Raises:
        FileNotFoundError: Propagated from StateStore.load() when no draft exists.
        ValueError:        Propagated from BlogJob when a transition is invalid.
    """

    def __init__(self, store: StateStore | None = None) -> None:
        self._store = store or StateStore()

    # ---------------------------------------------------------------- #
    # review                                                             #
    # ---------------------------------------------------------------- #

    def review(self) -> BlogJob:
        """Load the current draft and transition DRAFT → REVIEWED.

        Idempotent for jobs already at or past REVIEWED: the job is
        displayed but the state is not modified.

        Returns:
            The job in REVIEWED (or later) state.

        Raises:
            FileNotFoundError: No draft exists.
        """
        job = self._store.load()
        if job.state == JobState.DRAFT:
            job = job.mark_reviewed()
            self._store.save(job)
        return job

    # ---------------------------------------------------------------- #
    # revise                                                             #
    # ---------------------------------------------------------------- #

    def revise(self, instruction: str) -> BlogJob:
        """Store a revision instruction and reset approvals per PRD rules.

        See BlogJob.revise() for the exact reset behaviour per state.

        Returns:
            The job in DRAFT state with revise_instruction set.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is in REJECTED state (terminal).
        """
        job = self._store.load()
        job = job.revise(instruction)
        self._store.save(job)
        return job

    # ---------------------------------------------------------------- #
    # approve_content                                                    #
    # ---------------------------------------------------------------- #

    # Minimum quality_score required to approve content (PRD §Quality Gate).
    # A draft below this threshold is not considered publish-ready.
    MIN_QUALITY_SCORE: int = 60

    def approve_content(self) -> BlogJob:
        """Transition REVIEWED → APPROVED_STEP_1 (content approval, step 1 of 2).

        Enforces the PRD quality gate: rejects approval when quality_score
        is set and falls below MIN_QUALITY_SCORE (default 60).

        Returns:
            The job in APPROVED_STEP_1 state with content_approved_at set.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is not in REVIEWED state, or quality_score is
                        below the minimum threshold.
        """
        job = self._store.load()
        if (
            job.quality_score is not None
            and job.quality_score < self.MIN_QUALITY_SCORE
        ):
            raise ValueError(
                f"Quality score {job.quality_score}/100 is below the minimum "
                f"{self.MIN_QUALITY_SCORE}. Run 'brewpress revise' to improve "
                "the draft before approving."
            )
        job = job.approve_content()
        self._store.save(job)
        return job

    # ---------------------------------------------------------------- #
    # approve_publish                                                    #
    # ---------------------------------------------------------------- #

    def approve_publish(self, live: bool = False) -> BlogJob:
        """Transition APPROVED_STEP_1 → APPROVED_STEP_2 (publish approval, step 2 of 2).

        Args:
            live: When True, sets publish_live=True on the job.
                  This flag is passed explicitly from the CLI ``--live`` flag.
                  It is never inferred from context.

        Returns:
            The job in APPROVED_STEP_2 state with publish_approved_at set.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is not in APPROVED_STEP_1 state.
        """
        job = self._store.load()
        job = job.approve_publish(live=live)
        self._store.save(job)
        return job

    # ---------------------------------------------------------------- #
    # reject                                                             #
    # ---------------------------------------------------------------- #

    def reject(self, reason: str = "", force: bool = False) -> BlogJob:
        """Transition any non-terminal state → REJECTED.

        Args:
            reason: Optional human-readable rejection reason.
            force:  When True, allow rejection from APPROVED_STEP_2.

        Returns:
            The job in REJECTED state.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Invalid state transition (see BlogJob.reject).
        """
        job = self._store.load()
        job = job.reject(reason=reason, force=force)
        self._store.save(job)
        return job

    # ---------------------------------------------------------------- #
    # rollback_publish_approval                                          #
    # ---------------------------------------------------------------- #

    def rollback_publish_approval(self) -> BlogJob:
        """Roll back APPROVED_STEP_2 → APPROVED_STEP_1 after a failed publish.

        Called by the CLI when the WordPress publish request raises
        PublishError, so the job is left in a retryable state rather than
        stuck in APPROVED_STEP_2 indefinitely.

        Returns:
            The job restored to APPROVED_STEP_1.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is not in APPROVED_STEP_2.
        """
        from brewpress.models import JobState

        job = self._store.load()
        if job.state != JobState.APPROVED_STEP_2:
            raise ValueError(
                f"rollback_publish_approval() requires state APPROVED_STEP_2, "
                f"got {job.state.value!r}."
            )
        job = job.model_copy(update={"state": JobState.APPROVED_STEP_1})
        self._store.save(job)
        return job
