"""BrewPress domain models.

BlogJob is the central state object. It is immutable (frozen=True) — every
state transition returns a new instance via model_copy(). Direct field
assignment raises an error.

State machine:

    DRAFT ──► REVIEWED ──► APPROVED_STEP_1 ──► APPROVED_STEP_2
      ▲                                               │
      └──────────────── (new draft run) ◄─────────────┘

    Any non-terminal state ──► REJECTED

Transitions:
    mark_reviewed()     DRAFT          → REVIEWED
    approve_content()   REVIEWED       → APPROVED_STEP_1
    approve_publish()   APPROVED_STEP_1 → APPROVED_STEP_2
    reject(reason)      any            → REJECTED
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED_STEP_1 = "approved_step_1"
    APPROVED_STEP_2 = "approved_step_2"
    REJECTED = "rejected"


class JobIntent(StrEnum):
    NEW_POST = "new_post"
    UPDATE_POST = "update_post"


class BlogJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    state: JobState = JobState.DRAFT
    intent: JobIntent = JobIntent.NEW_POST

    # Content fields — populated after generation
    title: str = ""
    slug: str = ""
    meta_description: str = ""
    excerpt: str = ""
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)
    draft_body_md: str = ""
    is_single_topic: bool = True
    quality_score: int | None = None
    quality_gaps: list[str] = Field(default_factory=list)

    # Narrative structure fields — from storytelling prompt layer
    hook: str = ""   # 2–3 sentence opening hook (Problem → Solution)
    cta: str = ""    # call-to-action closing sentence

    # Approval timestamps
    content_approved_at: str | None = None
    publish_approved_at: str | None = None

    # WordPress state
    wp_post_id: int | None = None
    target_wp_post_id: int | None = None  # required when intent=UPDATE_POST

    # Publish intent — set by approve_publish(live=True)
    publish_live: bool = False

    # Content type — True when diff/PR URL/commands are present (PRD §Content Types)
    is_code_post: bool = False

    # SEO score — set by SEOAgent.optimize(), used by CriticAgent for deterministic seo_quality
    seo_score: int | None = None

    # Revision — instruction and loop iteration counter
    revise_instruction: str = ""
    revision_attempt: int = 0  # incremented per loop pass in Orchestrator

    # Rejection
    rejected_reason: str = ""

    # ------------------------------------------------------------------ #
    # State transitions — each returns a new immutable BlogJob instance.  #
    # ------------------------------------------------------------------ #

    def mark_reviewed(self) -> BlogJob:
        """Transition DRAFT → REVIEWED after generation output is shown."""
        if self.state != JobState.DRAFT:
            raise ValueError(
                f"mark_reviewed() requires state DRAFT, got {self.state.value!r}."
            )
        return self.model_copy(update={"state": JobState.REVIEWED})

    def approve_content(self) -> BlogJob:
        """Transition REVIEWED → APPROVED_STEP_1 (content approval, step 1 of 2)."""
        if self.state != JobState.REVIEWED:
            raise ValueError(
                f"approve_content() requires state REVIEWED, got {self.state.value!r}. "
                "Run 'brewpress review' first."
            )
        return self.model_copy(
            update={
                "state": JobState.APPROVED_STEP_1,
                "content_approved_at": datetime.now(UTC).isoformat(),
            }
        )

    def approve_publish(self, live: bool = False) -> BlogJob:
        """Transition APPROVED_STEP_1 → APPROVED_STEP_2 (publish approval, step 2 of 2).

        Args:
            live: When True, instructs the WordPress agent to publish live instead
                  of saving as a draft. Maps to ``approve_publish publish=true``
                  in the PRD review command surface. Never inferred implicitly.
        """
        if self.state != JobState.APPROVED_STEP_1:
            raise ValueError(
                f"approve_publish() requires state APPROVED_STEP_1, "
                f"got {self.state.value!r}. Run 'brewpress approve-content' first."
            )
        if self.intent == JobIntent.UPDATE_POST and self.target_wp_post_id is None:
            raise ValueError(
                "approve_publish() on an UPDATE_POST job requires target_wp_post_id "
                "to be set. Provide the WordPress post ID to update."
            )
        return self.model_copy(
            update={
                "state": JobState.APPROVED_STEP_2,
                "publish_approved_at": datetime.now(UTC).isoformat(),
                "publish_live": live,
            }
        )

    def revise(self, instruction: str) -> BlogJob:
        """Store a revision instruction and reset approvals per PRD §Approval Reset Rules.

        Reset behaviour:
            DRAFT            → DRAFT  (no approval to reset; stores instruction)
            REVIEWED         → DRAFT  (not yet approved; re-generation needed)
            APPROVED_STEP_1  → DRAFT  (resets content approval and timestamp)
            APPROVED_STEP_2  → DRAFT  (resets both approvals, timestamps, and publish_live)
            REJECTED         → raises ValueError (terminal state)
        """
        if self.state == JobState.REJECTED:
            raise ValueError(
                "Cannot revise a rejected job. Run 'brewpress draft' to start a new job."
            )

        update: dict[str, Any] = {
            "state": JobState.DRAFT,
            "revise_instruction": instruction,
        }

        # reset content approval when it was already set
        if self.state in (JobState.APPROVED_STEP_1, JobState.APPROVED_STEP_2):
            update["content_approved_at"] = None

        # reset publish approval when it was already set
        if self.state == JobState.APPROVED_STEP_2:
            update["publish_approved_at"] = None
            update["publish_live"] = False

        return self.model_copy(update=update)

    def reject(self, reason: str = "", force: bool = False) -> BlogJob:
        """Transition any non-terminal state → REJECTED.

        Args:
            reason: Optional human-readable rejection reason.
            force:  When True, allow rejection even from APPROVED_STEP_2
                    (e.g. after a failed publish where rollback isn't viable).
        """
        if self.state == JobState.REJECTED:
            raise ValueError(
                "Job is already in a terminal REJECTED state and cannot be rejected again."
            )
        if self.state == JobState.APPROVED_STEP_2 and not force:
            raise ValueError(
                "Cannot reject a job in APPROVED_STEP_2 state. "
                "Use 'brewpress reject --force' to override, or "
                "'brewpress approve-publish' to retry publishing."
            )
        return self.model_copy(
            update={"state": JobState.REJECTED, "rejected_reason": reason}
        )

    def to_json(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (enum values as strings)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BlogJob:
        """Deserialize from a JSON-compatible dict."""
        return cls.model_validate(data)
