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

    def approve_content(self) -> BlogJob:
        """Transition REVIEWED → APPROVED_STEP_1 (content approval, step 1 of 2).

        Returns:
            The job in APPROVED_STEP_1 state with content_approved_at set.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is not in REVIEWED state.
        """
        job = self._store.load()
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

    def reject(self, reason: str = "") -> BlogJob:
        """Transition any non-terminal state → REJECTED.

        Returns:
            The job in REJECTED state.

        Raises:
            FileNotFoundError: No draft exists.
            ValueError: Job is already in a terminal state.
        """
        job = self._store.load()
        job = job.reject(reason=reason)
        self._store.save(job)
        return job
