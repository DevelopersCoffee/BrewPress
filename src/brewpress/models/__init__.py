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
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED_STEP_1 = "approved_step_1"
    APPROVED_STEP_2 = "approved_step_2"
    REJECTED = "rejected"


class JobIntent(str, Enum):
    NEW_POST = "new_post"
    UPDATE_POST = "update_post"


class BlogJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    state: JobState = JobState.DRAFT
    intent: JobIntent = JobIntent.NEW_POST

    # Content fields — populated after generation
    title: str = ""
    slug: str = ""
    meta_description: str = ""
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)
    draft_body_md: str = ""
    is_single_topic: bool = True
    quality_score: int | None = None
    quality_gaps: list[str] = Field(default_factory=list)

    # Approval timestamps
    content_approved_at: str | None = None
    publish_approved_at: str | None = None

    # WordPress state
    wp_post_id: int | None = None
    target_wp_post_id: int | None = None  # required when intent=UPDATE_POST

    # Rejection
    rejected_reason: str = ""

    # ------------------------------------------------------------------ #
    # State transitions — each returns a new immutable BlogJob instance.  #
    # ------------------------------------------------------------------ #

    def mark_reviewed(self) -> "BlogJob":
        """Transition DRAFT → REVIEWED after generation output is shown."""
        if self.state != JobState.DRAFT:
            raise ValueError(
                f"mark_reviewed() requires state DRAFT, got {self.state.value!r}."
            )
        return self.model_copy(update={"state": JobState.REVIEWED})

    def approve_content(self) -> "BlogJob":
        """Transition REVIEWED → APPROVED_STEP_1 (content approval, step 1 of 2)."""
        if self.state != JobState.REVIEWED:
            raise ValueError(
                f"approve_content() requires state REVIEWED, got {self.state.value!r}. "
                "Run 'brewpress review' first."
            )
        return self.model_copy(
            update={
                "state": JobState.APPROVED_STEP_1,
                "content_approved_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def approve_publish(self) -> "BlogJob":
        """Transition APPROVED_STEP_1 → APPROVED_STEP_2 (publish approval, step 2 of 2)."""
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
                "publish_approved_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def reject(self, reason: str = "") -> "BlogJob":
        """Transition any non-terminal state → REJECTED."""
        if self.state in (JobState.APPROVED_STEP_2, JobState.REJECTED):
            raise ValueError(
                f"Cannot reject a job in terminal state {self.state.value!r}."
            )
        return self.model_copy(
            update={"state": JobState.REJECTED, "rejected_reason": reason}
        )

    def to_json(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (enum values as strings)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BlogJob":
        """Deserialize from a JSON-compatible dict."""
        return cls.model_validate(data)
