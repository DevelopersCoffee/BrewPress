"""Tests for brewpress.review_gate — ReviewGate state transitions,
format_draft display, and CLI command routing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from brewpress.models import BlogJob, JobIntent, JobState
from brewpress.review_gate import ReviewGate, format_draft
from brewpress.state_store import StateStore

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _store(tmp_path: Path) -> StateStore:
    return StateStore(path=tmp_path / "last_draft.json")


def _draft_job(**overrides: object) -> BlogJob:
    """Minimal BlogJob in DRAFT state."""
    base: dict = {
        "title": "Java 21 Virtual Threads",
        "slug": "java-21-virtual-threads",
        "meta_description": "A practical guide to virtual threads for Java developers.",
        "primary_keyword": "Java 21 virtual threads",
        "secondary_keywords": ["project loom", "java concurrency", "jdk 21"],
        "outline": ["Introduction", "Migration", "Benchmarks"],
        "draft_body_md": "## Introduction\n\nVirtual threads simplify concurrency.",
        "quality_score": 80,
        "quality_gaps": ["missing benchmark numbers"],
    }
    base.update(overrides)
    return BlogJob(**base)


def _gate(tmp_path: Path, initial: BlogJob | None = None) -> ReviewGate:
    store = _store(tmp_path)
    if initial is not None:
        store.save(initial)
    return ReviewGate(store=store)


# ------------------------------------------------------------------ #
# format_draft — content assertions                                    #
# ------------------------------------------------------------------ #


def test_format_draft_contains_title() -> None:
    job = _draft_job()
    assert "Java 21 Virtual Threads" in format_draft(job)


def test_format_draft_contains_state() -> None:
    job = _draft_job()
    assert "draft" in format_draft(job)


def test_format_draft_contains_slug() -> None:
    job = _draft_job()
    assert "java-21-virtual-threads" in format_draft(job)


def test_format_draft_contains_primary_keyword() -> None:
    job = _draft_job()
    assert "Java 21 virtual threads" in format_draft(job)


def test_format_draft_contains_secondary_keywords() -> None:
    job = _draft_job()
    output = format_draft(job)
    assert "project loom" in output
    assert "java concurrency" in output


def test_format_draft_contains_quality_score() -> None:
    job = _draft_job(quality_score=85)
    assert "85" in format_draft(job)


def test_format_draft_contains_quality_gaps() -> None:
    job = _draft_job(quality_gaps=["needs more code examples"])
    assert "needs more code examples" in format_draft(job)


def test_format_draft_omits_quality_when_none() -> None:
    job = _draft_job(quality_score=None, quality_gaps=[])
    assert "Quality" not in format_draft(job)


def test_format_draft_contains_outline() -> None:
    job = _draft_job(outline=["Intro", "Deep Dive", "Conclusion"])
    output = format_draft(job)
    assert "Deep Dive" in output


def test_format_draft_contains_body() -> None:
    job = _draft_job(draft_body_md="## Hello\n\nWorld.")
    assert "## Hello" in format_draft(job)


def test_format_draft_is_str() -> None:
    assert isinstance(format_draft(_draft_job()), str)


# ------------------------------------------------------------------ #
# ReviewGate.review                                                    #
# ------------------------------------------------------------------ #


def test_review_transitions_draft_to_reviewed(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    job = gate.review()
    assert job.state == JobState.REVIEWED


def test_review_persists_reviewed_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save(_draft_job())
    ReviewGate(store=store).review()
    assert store.load().state == JobState.REVIEWED


def test_review_idempotent_on_reviewed_state(tmp_path: Path) -> None:
    reviewed = _draft_job().mark_reviewed()
    gate = _gate(tmp_path, reviewed)
    job = gate.review()
    assert job.state == JobState.REVIEWED


def test_review_idempotent_on_approved_step_1(tmp_path: Path) -> None:
    approved = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, approved)
    job = gate.review()
    assert job.state == JobState.APPROVED_STEP_1


def test_review_raises_when_no_draft(tmp_path: Path) -> None:
    gate = ReviewGate(store=_store(tmp_path))
    with pytest.raises(FileNotFoundError):
        gate.review()


def test_review_returns_blog_job(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    assert isinstance(gate.review(), BlogJob)


# ------------------------------------------------------------------ #
# ReviewGate.revise                                                    #
# ------------------------------------------------------------------ #


def test_revise_from_reviewed_resets_to_draft(tmp_path: Path) -> None:
    reviewed = _draft_job().mark_reviewed()
    gate = _gate(tmp_path, reviewed)
    job = gate.revise("shorten the intro")
    assert job.state == JobState.DRAFT


def test_revise_stores_instruction(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    job = gate.revise("add more code examples")
    assert job.revise_instruction == "add more code examples"


def test_revise_after_approve_content_clears_timestamp(tmp_path: Path) -> None:
    approved = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, approved)
    job = gate.revise("needs work")
    assert job.content_approved_at is None
    assert job.state == JobState.DRAFT


def test_revise_after_approve_publish_clears_both(tmp_path: Path) -> None:
    fully_approved = (
        _draft_job().mark_reviewed().approve_content().approve_publish()
    )
    gate = _gate(tmp_path, fully_approved)
    job = gate.revise("restructure")
    assert job.content_approved_at is None
    assert job.publish_approved_at is None
    assert job.publish_live is False


def test_revise_after_approve_publish_live_clears_live_flag(tmp_path: Path) -> None:
    live_approved = (
        _draft_job().mark_reviewed().approve_content().approve_publish(live=True)
    )
    gate = _gate(tmp_path, live_approved)
    job = gate.revise("not ready")
    assert job.publish_live is False


def test_revise_persists_change(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save(_draft_job())
    ReviewGate(store=store).revise("fix tone")
    assert store.load().revise_instruction == "fix tone"


def test_revise_rejected_raises(tmp_path: Path) -> None:
    rejected = _draft_job().reject(reason="off brand")
    gate = _gate(tmp_path, rejected)
    with pytest.raises(ValueError, match="rejected"):
        gate.revise("bring it back")


def test_revise_raises_when_no_draft(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReviewGate(store=_store(tmp_path)).revise("any instruction")


# ------------------------------------------------------------------ #
# ReviewGate.approve_content                                           #
# ------------------------------------------------------------------ #


def test_approve_content_transitions_reviewed(tmp_path: Path) -> None:
    reviewed = _draft_job().mark_reviewed()
    gate = _gate(tmp_path, reviewed)
    job = gate.approve_content()
    assert job.state == JobState.APPROVED_STEP_1


def test_approve_content_sets_timestamp(tmp_path: Path) -> None:
    reviewed = _draft_job().mark_reviewed()
    gate = _gate(tmp_path, reviewed)
    job = gate.approve_content()
    assert job.content_approved_at is not None


def test_approve_content_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save(_draft_job().mark_reviewed())
    ReviewGate(store=store).approve_content()
    assert store.load().state == JobState.APPROVED_STEP_1


def test_approve_content_from_draft_raises(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    with pytest.raises(ValueError, match="REVIEWED"):
        gate.approve_content()


def test_approve_content_from_approved_step_1_raises(tmp_path: Path) -> None:
    already = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, already)
    with pytest.raises(ValueError, match="REVIEWED"):
        gate.approve_content()


def test_approve_content_raises_when_no_draft(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReviewGate(store=_store(tmp_path)).approve_content()


# ------------------------------------------------------------------ #
# ReviewGate.approve_publish                                           #
# ------------------------------------------------------------------ #


def test_approve_publish_transitions_step1_to_step2(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, step1)
    job = gate.approve_publish()
    assert job.state == JobState.APPROVED_STEP_2


def test_approve_publish_default_not_live(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, step1)
    job = gate.approve_publish()
    assert job.publish_live is False


def test_approve_publish_live_sets_flag(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, step1)
    job = gate.approve_publish(live=True)
    assert job.publish_live is True


def test_approve_publish_sets_timestamp(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, step1)
    job = gate.approve_publish()
    assert job.publish_approved_at is not None


def test_approve_publish_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save(_draft_job().mark_reviewed().approve_content())
    ReviewGate(store=store).approve_publish()
    assert store.load().state == JobState.APPROVED_STEP_2


def test_approve_publish_from_draft_raises(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    with pytest.raises(ValueError, match="APPROVED_STEP_1"):
        gate.approve_publish()


def test_approve_publish_from_reviewed_raises(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job().mark_reviewed())
    with pytest.raises(ValueError, match="APPROVED_STEP_1"):
        gate.approve_publish()


def test_approve_publish_update_post_requires_target_id(tmp_path: Path) -> None:
    job = (
        BlogJob(intent=JobIntent.UPDATE_POST)
        .mark_reviewed()
        .approve_content()
    )
    gate = _gate(tmp_path, job)
    with pytest.raises(ValueError, match="target_wp_post_id"):
        gate.approve_publish()


def test_approve_publish_raises_when_no_draft(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReviewGate(store=_store(tmp_path)).approve_publish()


# ------------------------------------------------------------------ #
# ReviewGate.reject                                                    #
# ------------------------------------------------------------------ #


def test_reject_from_draft(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job())
    job = gate.reject(reason="off brand")
    assert job.state == JobState.REJECTED
    assert job.rejected_reason == "off brand"


def test_reject_from_reviewed(tmp_path: Path) -> None:
    gate = _gate(tmp_path, _draft_job().mark_reviewed())
    job = gate.reject()
    assert job.state == JobState.REJECTED


def test_reject_from_approved_step_1(tmp_path: Path) -> None:
    approved = _draft_job().mark_reviewed().approve_content()
    gate = _gate(tmp_path, approved)
    job = gate.reject(reason="scope changed")
    assert job.state == JobState.REJECTED


def test_reject_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save(_draft_job())
    ReviewGate(store=store).reject()
    assert store.load().state == JobState.REJECTED


def test_reject_terminal_raises(tmp_path: Path) -> None:
    rejected = _draft_job().reject()
    gate = _gate(tmp_path, rejected)
    with pytest.raises(ValueError, match="terminal"):
        gate.reject()


def test_reject_approved_step_2_raises(tmp_path: Path) -> None:
    fully_approved = _draft_job().mark_reviewed().approve_content().approve_publish()
    gate = _gate(tmp_path, fully_approved)
    with pytest.raises(ValueError, match="terminal"):
        gate.reject()


def test_reject_raises_when_no_draft(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ReviewGate(store=_store(tmp_path)).reject()


# ------------------------------------------------------------------ #
# CLI routing — review commands call ReviewGate                        #
# ------------------------------------------------------------------ #


def _run_cli(
    args: list[str], tmp_path: Path, initial: BlogJob | None = None
) -> tuple[int, str, str]:
    """Run main() with patched StateStore path and captured output."""
    import io
    from unittest.mock import patch

    from brewpress.cli import main

    state_file = tmp_path / "last_draft.json"
    if initial is not None:
        StateStore(path=state_file).save(initial)

    old_argv = sys.argv
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    sys.argv = ["brewpress"] + args

    try:
        with (
            patch("brewpress.review_gate.StateStore", lambda: StateStore(path=state_file)),
            patch("sys.stdout", out_buf),
            patch("sys.stderr", err_buf),
        ):
            rc = main()
    finally:
        sys.argv = old_argv

    return rc, out_buf.getvalue(), err_buf.getvalue()


def test_cli_review_exits_zero(tmp_path: Path) -> None:
    rc, _, _ = _run_cli(["review"], tmp_path, initial=_draft_job())
    assert rc == 0


def test_cli_review_prints_title(tmp_path: Path) -> None:
    _, out, _ = _run_cli(["review"], tmp_path, initial=_draft_job())
    assert "Java 21 Virtual Threads" in out


def test_cli_review_no_draft_exits_one(tmp_path: Path) -> None:
    rc, _, err = _run_cli(["review"], tmp_path)
    assert rc == 1
    assert err.strip()


def test_cli_revise_exits_zero(tmp_path: Path) -> None:
    rc, out, _ = _run_cli(["revise", "shorten intro"], tmp_path, initial=_draft_job())
    assert rc == 0
    assert "Revision recorded" in out


def test_cli_revise_no_draft_exits_one(tmp_path: Path) -> None:
    rc, _, err = _run_cli(["revise", "fix it"], tmp_path)
    assert rc == 1


def test_cli_approve_content_exits_zero(tmp_path: Path) -> None:
    reviewed = _draft_job().mark_reviewed()
    rc, out, _ = _run_cli(["approve-content"], tmp_path, initial=reviewed)
    assert rc == 0
    assert "step 1" in out.lower() or "approved" in out.lower()


def test_cli_approve_content_wrong_state_exits_one(tmp_path: Path) -> None:
    rc, _, err = _run_cli(["approve-content"], tmp_path, initial=_draft_job())
    assert rc == 1


def test_cli_approve_publish_exits_zero(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    rc, out, _ = _run_cli(["approve-publish"], tmp_path, initial=step1)
    assert rc == 0
    assert "draft" in out.lower() or "approved" in out.lower()


def test_cli_approve_publish_live_exits_zero(tmp_path: Path) -> None:
    step1 = _draft_job().mark_reviewed().approve_content()
    rc, out, _ = _run_cli(["approve-publish", "--live"], tmp_path, initial=step1)
    assert rc == 0
    assert "live" in out.lower()


def test_cli_approve_publish_wrong_state_exits_one(tmp_path: Path) -> None:
    rc, _, err = _run_cli(["approve-publish"], tmp_path, initial=_draft_job())
    assert rc == 1


def test_cli_reject_exits_zero(tmp_path: Path) -> None:
    rc, out, _ = _run_cli(["reject"], tmp_path, initial=_draft_job())
    assert rc == 0
    assert "rejected" in out.lower()


def test_cli_reject_with_reason_exits_zero(tmp_path: Path) -> None:
    rc, _, _ = _run_cli(["reject", "--reason", "off brand"], tmp_path, initial=_draft_job())
    assert rc == 0


def test_cli_reject_no_draft_exits_one(tmp_path: Path) -> None:
    rc, _, err = _run_cli(["reject"], tmp_path)
    assert rc == 1
