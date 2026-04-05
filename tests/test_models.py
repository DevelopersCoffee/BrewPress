"""Tests for brewpress.models — BlogJob state machine."""

from __future__ import annotations

import pytest

from brewpress.models import BlogJob, JobIntent, JobState

# ------------------------------------------------------------------ #
# Construction                                                         #
# ------------------------------------------------------------------ #


def test_default_construction() -> None:
    job = BlogJob()
    assert job.state == JobState.DRAFT
    assert job.intent == JobIntent.NEW_POST
    assert job.schema_version == 1
    assert job.wp_post_id is None
    assert job.target_wp_post_id is None
    assert job.content_approved_at is None
    assert job.publish_approved_at is None
    assert job.job_id  # non-empty string


def test_job_ids_are_unique() -> None:
    a = BlogJob()
    b = BlogJob()
    assert a.job_id != b.job_id


def test_generated_at_is_set() -> None:
    job = BlogJob()
    assert job.generated_at  # ISO8601 string


def test_frozen_prevents_direct_assignment() -> None:
    from pydantic import ValidationError
    job = BlogJob()
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        job.state = JobState.REVIEWED  # type: ignore[misc]


# ------------------------------------------------------------------ #
# JSON round-trip                                                      #
# ------------------------------------------------------------------ #


def test_json_round_trip_empty_job() -> None:
    job = BlogJob()
    restored = BlogJob.from_json(job.to_json())
    assert restored == job


def test_json_round_trip_preserves_enums() -> None:
    job = BlogJob(intent=JobIntent.UPDATE_POST, target_wp_post_id=42)
    data = job.to_json()
    assert data["intent"] == "update_post"
    assert data["state"] == "draft"
    restored = BlogJob.from_json(data)
    assert restored.intent == JobIntent.UPDATE_POST
    assert restored.target_wp_post_id == 42


def test_json_round_trip_after_transitions() -> None:
    job = BlogJob().mark_reviewed().approve_content()
    restored = BlogJob.from_json(job.to_json())
    assert restored.state == JobState.APPROVED_STEP_1
    assert restored.content_approved_at == job.content_approved_at


# ------------------------------------------------------------------ #
# mark_reviewed                                                        #
# ------------------------------------------------------------------ #


def test_mark_reviewed_from_draft() -> None:
    job = BlogJob().mark_reviewed()
    assert job.state == JobState.REVIEWED


def test_mark_reviewed_returns_new_instance() -> None:
    original = BlogJob()
    reviewed = original.mark_reviewed()
    assert original.state == JobState.DRAFT
    assert reviewed.state == JobState.REVIEWED
    assert original is not reviewed


def test_mark_reviewed_invalid_from_reviewed() -> None:
    job = BlogJob().mark_reviewed()
    with pytest.raises(ValueError, match="DRAFT"):
        job.mark_reviewed()


def test_mark_reviewed_invalid_from_approved_step_1() -> None:
    job = BlogJob().mark_reviewed().approve_content()
    with pytest.raises(ValueError, match="DRAFT"):
        job.mark_reviewed()


# ------------------------------------------------------------------ #
# approve_content                                                      #
# ------------------------------------------------------------------ #


def test_approve_content_from_reviewed() -> None:
    job = BlogJob().mark_reviewed().approve_content()
    assert job.state == JobState.APPROVED_STEP_1
    assert job.content_approved_at is not None


def test_approve_content_sets_timestamp() -> None:
    job = BlogJob().mark_reviewed().approve_content()
    assert "T" in job.content_approved_at  # ISO8601


def test_approve_content_invalid_from_draft() -> None:
    with pytest.raises(ValueError, match="REVIEWED"):
        BlogJob().approve_content()


def test_approve_content_invalid_from_approved_step_1() -> None:
    job = BlogJob().mark_reviewed().approve_content()
    with pytest.raises(ValueError, match="REVIEWED"):
        job.approve_content()


def test_approve_content_invalid_from_approved_step_2() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    with pytest.raises(ValueError, match="REVIEWED"):
        job.approve_content()


# ------------------------------------------------------------------ #
# approve_publish                                                      #
# ------------------------------------------------------------------ #


def test_approve_publish_from_approved_step_1() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    assert job.state == JobState.APPROVED_STEP_2
    assert job.publish_approved_at is not None


def test_approve_publish_sets_timestamp() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    assert "T" in job.publish_approved_at


def test_approve_publish_default_is_not_live() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    assert job.publish_live is False


def test_approve_publish_live_sets_flag() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish(live=True)
    assert job.publish_live is True
    assert job.state == JobState.APPROVED_STEP_2


def test_approve_publish_invalid_from_draft() -> None:
    with pytest.raises(ValueError, match="APPROVED_STEP_1"):
        BlogJob().approve_publish()


def test_approve_publish_invalid_from_reviewed() -> None:
    with pytest.raises(ValueError, match="APPROVED_STEP_1"):
        BlogJob().mark_reviewed().approve_publish()


def test_approve_publish_update_post_requires_target_id() -> None:
    job = BlogJob(intent=JobIntent.UPDATE_POST).mark_reviewed().approve_content()
    with pytest.raises(ValueError, match="target_wp_post_id"):
        job.approve_publish()


def test_approve_publish_update_post_with_target_id() -> None:
    job = (
        BlogJob(intent=JobIntent.UPDATE_POST, target_wp_post_id=99)
        .mark_reviewed()
        .approve_content()
        .approve_publish()
    )
    assert job.state == JobState.APPROVED_STEP_2


# ------------------------------------------------------------------ #
# reject                                                               #
# ------------------------------------------------------------------ #


def test_reject_from_draft() -> None:
    job = BlogJob().reject(reason="not relevant")
    assert job.state == JobState.REJECTED
    assert job.rejected_reason == "not relevant"


def test_reject_from_reviewed() -> None:
    job = BlogJob().mark_reviewed().reject()
    assert job.state == JobState.REJECTED


def test_reject_from_approved_step_1() -> None:
    job = BlogJob().mark_reviewed().approve_content().reject(reason="off brand")
    assert job.state == JobState.REJECTED
    assert job.rejected_reason == "off brand"


def test_reject_empty_reason() -> None:
    job = BlogJob().reject()
    assert job.rejected_reason == ""


def test_reject_approved_step_2_raises_without_force() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    with pytest.raises(ValueError, match="--force"):
        job.reject()


def test_reject_approved_step_2_with_force() -> None:
    job = BlogJob().mark_reviewed().approve_content().approve_publish()
    result = job.reject(force=True)
    assert result.state == JobState.REJECTED


def test_reject_already_rejected_raises() -> None:
    job = BlogJob().reject()
    with pytest.raises(ValueError, match="terminal"):
        job.reject()


# ------------------------------------------------------------------ #
# Full happy-path chain                                                #
# ------------------------------------------------------------------ #


def test_full_new_post_approval_chain() -> None:
    job = (
        BlogJob()
        .mark_reviewed()
        .approve_content()
        .approve_publish()
    )
    assert job.state == JobState.APPROVED_STEP_2
    assert job.content_approved_at is not None
    assert job.publish_approved_at is not None


def test_full_update_post_chain() -> None:
    job = (
        BlogJob(intent=JobIntent.UPDATE_POST, target_wp_post_id=7)
        .mark_reviewed()
        .approve_content()
        .approve_publish()
    )
    assert job.state == JobState.APPROVED_STEP_2
    assert job.target_wp_post_id == 7


# ------------------------------------------------------------------ #
# revise                                                               #
# ------------------------------------------------------------------ #


def test_revise_from_draft_stays_draft() -> None:
    """PRD: revise before any approval — no reset needed."""
    job = BlogJob().revise("make the intro shorter")
    assert job.state == JobState.DRAFT
    assert job.revise_instruction == "make the intro shorter"


def test_revise_from_reviewed_resets_to_draft() -> None:
    """PRD: revise before any approval — no approval to clear, re-generation needed."""
    job = BlogJob().mark_reviewed().revise("add more code examples")
    assert job.state == JobState.DRAFT
    assert job.revise_instruction == "add more code examples"


def test_revise_from_draft_does_not_touch_timestamps() -> None:
    job = BlogJob().revise("fix tone")
    assert job.content_approved_at is None
    assert job.publish_approved_at is None


def test_revise_after_approve_content_resets_content_approval() -> None:
    """PRD: revise after approve_content → reset content approval."""
    job = BlogJob().mark_reviewed().approve_content().revise("shorten conclusion")
    assert job.state == JobState.DRAFT
    assert job.content_approved_at is None
    assert job.revise_instruction == "shorten conclusion"


def test_revise_after_approve_content_does_not_clear_publish() -> None:
    # publish_approved_at was never set — confirm it stays None
    job = BlogJob().mark_reviewed().approve_content().revise("tweak intro")
    assert job.publish_approved_at is None


def test_revise_after_approve_publish_resets_both_approvals() -> None:
    """PRD: revise after approve_publish → reset both approvals."""
    job = (
        BlogJob()
        .mark_reviewed()
        .approve_content()
        .approve_publish()
        .revise("restructure the whole thing")
    )
    assert job.state == JobState.DRAFT
    assert job.content_approved_at is None
    assert job.publish_approved_at is None
    assert job.revise_instruction == "restructure the whole thing"


def test_revise_after_approve_publish_live_clears_publish_live() -> None:
    """publish_live must be cleared when reverting from APPROVED_STEP_2."""
    job = (
        BlogJob()
        .mark_reviewed()
        .approve_content()
        .approve_publish(live=True)
        .revise("not ready yet")
    )
    assert job.publish_live is False


def test_revise_returns_new_instance() -> None:
    original = BlogJob()
    revised = original.revise("change tone")
    assert original is not revised
    assert original.revise_instruction == ""


def test_revise_rejected_raises() -> None:
    """Cannot revise a terminal REJECTED job."""
    job = BlogJob().reject(reason="off brand")
    with pytest.raises(ValueError, match="rejected"):
        job.revise("never mind, bring it back")
