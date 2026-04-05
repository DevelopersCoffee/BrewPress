"""Tests for brewpress.orchestrator — draft and publish pipeline wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brewpress.execution_layer import CommandResult, ExecutionTrace
from brewpress.media_agent import MediaManifest, MediaType
from brewpress.models import BlogJob, JobState
from brewpress.orchestrator import DraftResult, Orchestrator
from brewpress.state_store import StateStore
from brewpress.work_ingestion import WorkContext
from brewpress.wp_client import AmbiguousMatchError, PublishError


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _job(**overrides: object) -> BlogJob:
    base: dict = {
        "title": "Java Virtual Threads",
        "slug": "java-virtual-threads",
        "meta_description": "Guide to virtual threads.",
        "excerpt": "Virtual threads are lightweight.",
        "primary_keyword": "java virtual threads",
        "secondary_keywords": ["project loom", "jdk 21", "concurrency"],
        "tags": ["java"],
        "categories": ["Backend"],
        "draft_body_md": "## Intro\n\nVirtual threads.",
    }
    base.update(overrides)
    return BlogJob(**base)


def _reviewed_job(**overrides: object) -> BlogJob:
    return _job(**overrides).mark_reviewed()


def _approved_step2_job(**overrides: object) -> BlogJob:
    return (
        _job(**overrides)
        .mark_reviewed()
        .approve_content()
        .approve_publish(live=False)
    )


def _make_store(job: BlogJob | None = None, tmp_path: Path | None = None) -> StateStore:
    """Build a StateStore backed by a temp file, pre-seeded with a job."""
    store = StateStore(path=tmp_path / "last_draft.json") if tmp_path else StateStore()
    if job is not None:
        store.save(job)
    return store


def _make_draft_agent(returned_job: BlogJob) -> MagicMock:
    agent = MagicMock()
    agent.generate.return_value = returned_job
    return agent


def _empty_trace(job_id: str = "j1") -> ExecutionTrace:
    return ExecutionTrace(job_id=job_id, results=[], completed_at="")


def _success_trace(job_id: str = "j1") -> ExecutionTrace:
    result = CommandResult(
        command="mvn test",
        stdout="BUILD SUCCESS\n",
        stderr="",
        exit_code=0,
        duration_ms=100,
        ran_at="2024-06-01T00:00:00+00:00",
    )
    return ExecutionTrace(job_id=job_id, results=[result], completed_at="2024-06-01T00:00:01+00:00")


# ------------------------------------------------------------------ #
# DraftResult                                                          #
# ------------------------------------------------------------------ #


def test_draft_result_is_frozen() -> None:
    job = _reviewed_job()
    result = DraftResult(job=job, media_gaps=[])
    with pytest.raises(Exception):
        result.job = _reviewed_job()  # type: ignore[misc]


def test_draft_result_stores_job_and_gaps() -> None:
    job = _reviewed_job()
    result = DraftResult(job=job, media_gaps=["missing terminal screenshot"])
    assert result.job is job
    assert result.media_gaps == ["missing terminal screenshot"]


# ------------------------------------------------------------------ #
# Orchestrator.draft() — happy path                                    #
# ------------------------------------------------------------------ #


def test_draft_returns_draft_result(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest, \
         patch("brewpress.orchestrator.run_commands") as mock_run, \
         patch("brewpress.orchestrator.generate_for_code_post") as mock_gen, \
         patch("brewpress.orchestrator.validate_code_post_media") as mock_val:

        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx
        mock_run.return_value = _empty_trace()
        mock_gen.return_value = MediaManifest(job_id="j1", items=[])
        mock_val.return_value = []

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Java Virtual Threads")

    assert isinstance(result, DraftResult)


def test_draft_result_job_is_reviewed_state(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Java Virtual Threads")

    assert result.job.state == JobState.REVIEWED


def test_draft_passes_topic_to_ingest(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        orc.draft(topic="Rate limiting in Go", notes="some notes")

    mock_ingest.assert_called_once_with("Rate limiting in Go", "some notes", None, None)


def test_draft_passes_force_to_agent(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        orc.draft(topic="Topic", force=True)

    agent.generate.assert_called_once_with(ctx, force=True)


def test_draft_no_media_gaps_for_non_code_post(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Topic")

    assert result.media_gaps == []


def test_draft_saves_job_to_store(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Topic")

    saved = store.load()
    assert saved.job_id == result.job.job_id


# ------------------------------------------------------------------ #
# Orchestrator.draft() — code post path                               #
# ------------------------------------------------------------------ #


def test_draft_code_post_no_commands_returns_gap(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = True
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="", diff_path="fake.diff")

    assert len(result.media_gaps) == 1
    assert "add" in result.media_gaps[0].lower() or "command" in result.media_gaps[0].lower()


def test_draft_code_post_with_commands_runs_execution_layer(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest, \
         patch("brewpress.orchestrator.run_commands") as mock_run, \
         patch("brewpress.orchestrator.generate_for_code_post") as mock_gen, \
         patch("brewpress.orchestrator.validate_code_post_media") as mock_val:

        ctx = MagicMock()
        ctx.is_code_post = True
        ctx.commands = ["mvn test"]
        mock_ingest.return_value = ctx
        mock_run.return_value = _success_trace(job_id=draft_job.job_id)
        mock_gen.return_value = MediaManifest(job_id=draft_job.job_id, items=[])
        mock_val.return_value = []

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="", diff_path="fake.diff")

    mock_run.assert_called_once_with(["mvn test"], job_id=draft_job.job_id)
    assert result.media_gaps == []


def test_draft_code_post_media_gaps_propagated(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest, \
         patch("brewpress.orchestrator.run_commands") as mock_run, \
         patch("brewpress.orchestrator.generate_for_code_post") as mock_gen, \
         patch("brewpress.orchestrator.validate_code_post_media") as mock_val:

        ctx = MagicMock()
        ctx.is_code_post = True
        ctx.commands = ["mvn test"]
        mock_ingest.return_value = ctx
        mock_run.return_value = _success_trace()
        mock_gen.return_value = MediaManifest(job_id=draft_job.job_id, items=[])
        mock_val.return_value = ["Missing terminal screenshot"]

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="", diff_path="fake.diff")

    assert "Missing terminal screenshot" in result.media_gaps


# ------------------------------------------------------------------ #
# Orchestrator.draft() — error cases                                   #
# ------------------------------------------------------------------ #


def test_draft_requires_config_when_no_agent_injected(tmp_path: Path) -> None:
    store = _make_store(tmp_path=tmp_path)
    orc = Orchestrator(store=store)  # no draft_agent, no config

    with pytest.raises(ValueError, match="BrewPressConfig"):
        orc.draft(topic="Topic")


def test_draft_builds_agent_from_config_when_not_injected(tmp_path: Path) -> None:
    from brewpress.config import BrewPressConfig
    config = BrewPressConfig(google_api_key="fake-key")
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.DraftAgent") as MockAgent, \
         patch("brewpress.orchestrator.ingest") as mock_ingest:

        mock_instance = MagicMock()
        mock_instance.generate.return_value = _job()
        MockAgent.return_value = mock_instance

        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store)
        orc.draft(topic="Topic", config=config)

    MockAgent.assert_called_once_with(config)


def test_draft_propagates_agent_value_error(tmp_path: Path) -> None:
    agent = MagicMock()
    agent.generate.side_effect = ValueError("multi-topic without force")
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        with pytest.raises(ValueError, match="multi-topic"):
            orc.draft(topic="Topic")


# ------------------------------------------------------------------ #
# Orchestrator.publish() — happy path                                  #
# ------------------------------------------------------------------ #


def test_publish_returns_updated_job(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    published = approved.model_copy(update={"wp_post_id": 42})
    wp.publish.return_value = published

    orc = Orchestrator(store=store, wp_client=wp)
    result = orc.publish()

    assert result.wp_post_id == 42


def test_publish_saves_updated_job_to_store(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    published = approved.model_copy(update={"wp_post_id": 99})
    wp.publish.return_value = published

    orc = Orchestrator(store=store, wp_client=wp)
    orc.publish()

    saved = store.load()
    assert saved.wp_post_id == 99


def test_publish_calls_wp_client_with_job(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, wp_client=wp)
    orc.publish()

    wp.publish.assert_called_once_with(approved, featured_media_id=None)


def test_publish_builds_client_from_config_when_not_injected(tmp_path: Path) -> None:
    from brewpress.config import BrewPressConfig
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)
    config = BrewPressConfig(
        wp_url="https://example.com",
        wp_username="admin",
        wp_app_password="secret",
    )

    with patch("brewpress.orchestrator.WordPressClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.publish.return_value = approved.model_copy(update={"wp_post_id": 1})
        MockClient.return_value = mock_instance

        orc = Orchestrator(store=store)
        orc.publish(config=config)

    MockClient.assert_called_once_with(config)


# ------------------------------------------------------------------ #
# Orchestrator.publish() — error cases                                 #
# ------------------------------------------------------------------ #


def test_publish_raises_if_no_draft_exists(tmp_path: Path) -> None:
    store = _make_store(tmp_path=tmp_path)  # empty store
    orc = Orchestrator(store=store, wp_client=MagicMock())

    with pytest.raises(FileNotFoundError):
        orc.publish()


def test_publish_raises_if_wrong_state(tmp_path: Path) -> None:
    # Job in REVIEWED state, not APPROVED_STEP_2
    reviewed = _reviewed_job()
    store = _make_store(job=reviewed, tmp_path=tmp_path)

    orc = Orchestrator(store=store, wp_client=MagicMock())
    with pytest.raises(ValueError, match="approved_step_2"):
        orc.publish()


def test_publish_raises_if_no_client_and_no_config(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    orc = Orchestrator(store=store)  # no wp_client, no config
    with pytest.raises(ValueError, match="BrewPressConfig"):
        orc.publish()


def test_publish_writes_failure_bundle_on_publish_error(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    wp.publish.side_effect = PublishError("502 Bad Gateway")

    bundle_dir = tmp_path / "bundles"

    orc = Orchestrator(store=store, wp_client=wp)
    with pytest.raises(PublishError):
        orc.publish(bundle_dir=bundle_dir)

    # bundle file should exist
    bundles = list(bundle_dir.glob("failure_bundle_*.json"))
    assert len(bundles) == 1


def test_publish_re_raises_ambiguous_match_error(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    wp.publish.side_effect = AmbiguousMatchError(
        "Java Virtual Threads", [{"id": 1}, {"id": 2}]
    )

    orc = Orchestrator(store=store, wp_client=wp)
    with pytest.raises(AmbiguousMatchError):
        orc.publish()


# ------------------------------------------------------------------ #
# Determinism guarantees                                               #
# ------------------------------------------------------------------ #


def test_no_ai_calls_in_publish(tmp_path: Path) -> None:
    """publish() must not call DraftAgent.generate()."""
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    agent = MagicMock()
    wp = MagicMock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, draft_agent=agent, wp_client=wp)
    orc.publish()

    agent.generate.assert_not_called()


def test_no_wp_calls_in_draft(tmp_path: Path) -> None:
    """draft() must not call WordPressClient.publish()."""
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)
    wp = MagicMock()

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent, wp_client=wp)
        orc.draft(topic="Topic")

    wp.publish.assert_not_called()


# ------------------------------------------------------------------ #
# is_code_post tagging                                                 #
# ------------------------------------------------------------------ #


def test_draft_tags_is_code_post_true_when_context_is_code_post(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest, \
         patch("brewpress.orchestrator.run_commands") as mock_run, \
         patch("brewpress.orchestrator.generate_for_code_post") as mock_gen, \
         patch("brewpress.orchestrator.validate_code_post_media") as mock_val:

        ctx = MagicMock()
        ctx.is_code_post = True
        ctx.commands = ["mvn test"]
        mock_ingest.return_value = ctx
        mock_run.return_value = _empty_trace()
        mock_gen.return_value = MediaManifest(job_id="j1", items=[])
        mock_val.return_value = []

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="", diff_path="fake.diff")

    assert result.job.is_code_post is True


def test_draft_tags_is_code_post_false_for_regular_post(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Topic")

    assert result.job.is_code_post is False


# ------------------------------------------------------------------ #
# auto_approve                                                         #
# ------------------------------------------------------------------ #


def test_draft_auto_approve_returns_approved_step_1(tmp_path: Path) -> None:
    draft_job = _job(quality_score=80)
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Topic", auto_approve=True)

    assert result.job.state == JobState.APPROVED_STEP_1


def test_draft_without_auto_approve_returns_reviewed(tmp_path: Path) -> None:
    draft_job = _job()
    agent = _make_draft_agent(draft_job)
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        orc = Orchestrator(store=store, draft_agent=agent)
        result = orc.draft(topic="Topic", auto_approve=False)

    assert result.job.state == JobState.REVIEWED
