"""Tests for brewpress.orchestrator — draft and publish pipeline wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brewpress.critic_agent import CriticResult, CriticScores
from brewpress.execution_layer import CommandResult, ExecutionTrace
from brewpress.media_agent import MediaManifest
from brewpress.models import BlogJob, JobState
from brewpress.orchestrator import DraftResult, Orchestrator, PipelineAgents
from brewpress.state_store import StateStore
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


def _passing_scores() -> CriticScores:
    return CriticScores(seo_quality=4, clarity=5, technical_accuracy=4, publish_readiness=4)


def _failing_scores() -> CriticScores:
    return CriticScores(seo_quality=2, clarity=3, technical_accuracy=4, publish_readiness=3)


def _pass_result() -> CriticResult:
    return CriticResult(
        verdict="pass",
        revision_instruction="",
        scores=_passing_scores(),
        failures=[],
    )


def _revise_result(instruction: str = "fix the hook section") -> CriticResult:
    return CriticResult(
        verdict="revise",
        revision_instruction=instruction,
        scores=_failing_scores(),
        failures=["hook is weak"],
    )


def _make_pipeline(
    draft_job: BlogJob | None = None,
    critic_results: list[CriticResult] | None = None,
) -> PipelineAgents:
    """Build a PipelineAgents with all mocked agents.

    critic_results: sequence of CriticResult to return on successive calls.
                    Defaults to [_pass_result()] (passes first time).
    """
    if draft_job is None:
        draft_job = _job()
    if critic_results is None:
        critic_results = [_pass_result()]

    writer = MagicMock()
    writer.generate.return_value = draft_job
    writer.generate_revision.return_value = draft_job

    structurer = MagicMock()
    structurer.structure.side_effect = lambda j: j  # identity

    seo = MagicMock()
    seo.optimize.side_effect = lambda j: j  # identity

    critic = MagicMock()
    critic.review.side_effect = critic_results

    return PipelineAgents(writer=writer, structurer=structurer, seo=seo, critic=critic)


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


def test_draft_result_pipeline_summary_defaults_empty() -> None:
    result = DraftResult(job=_reviewed_job(), media_gaps=[])
    assert result.pipeline_summary == ""


# ------------------------------------------------------------------ #
# PipelineAgents                                                       #
# ------------------------------------------------------------------ #


def test_pipeline_agents_defaults_all_none() -> None:
    p = PipelineAgents()
    assert p.writer is None
    assert p.structurer is None
    assert p.seo is None
    assert p.critic is None


# ------------------------------------------------------------------ #
# Orchestrator.draft() — happy path                                    #
# ------------------------------------------------------------------ #


def test_draft_returns_draft_result(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Java Virtual Threads")

    assert isinstance(result, DraftResult)


def test_draft_result_job_is_reviewed_state(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Java Virtual Threads")

    assert result.job.state == JobState.REVIEWED


def test_draft_passes_topic_to_ingest(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        Orchestrator(store=store, pipeline=pipeline).draft(
            topic="Rate limiting in Go", notes="some notes"
        )

    mock_ingest.assert_called_once_with("Rate limiting in Go", "some notes", None, None)


def test_draft_passes_force_to_writer(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic", force=True)

    pipeline.writer.generate.assert_called_once_with(ctx, force=True)


def test_draft_no_media_gaps_for_non_code_post(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert result.media_gaps == []


def test_draft_saves_job_to_store(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    saved = store.load()
    assert saved.job_id == result.job.job_id


# ------------------------------------------------------------------ #
# Orchestrator.draft() — code post path                               #
# ------------------------------------------------------------------ #


def test_draft_code_post_no_commands_returns_gap(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = True
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="", diff_path="fake.diff"
        )

    assert len(result.media_gaps) == 1
    assert "command" in result.media_gaps[0].lower()


def test_draft_code_post_with_commands_runs_execution_layer(tmp_path: Path) -> None:
    draft_job = _job()
    pipeline = _make_pipeline(draft_job=draft_job)
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

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="", diff_path="fake.diff"
        )

    mock_run.assert_called_once_with(["mvn test"], job_id=draft_job.job_id)
    assert result.media_gaps == []


def test_draft_code_post_media_gaps_propagated(tmp_path: Path) -> None:
    draft_job = _job()
    pipeline = _make_pipeline(draft_job=draft_job)
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

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="", diff_path="fake.diff"
        )

    assert "Missing terminal screenshot" in result.media_gaps


# ------------------------------------------------------------------ #
# Orchestrator.draft() — error cases                                   #
# ------------------------------------------------------------------ #


def test_draft_requires_config_when_no_pipeline_injected(tmp_path: Path) -> None:
    store = _make_store(tmp_path=tmp_path)
    orc = Orchestrator(store=store)  # no pipeline, no config

    with pytest.raises(ValueError, match="BrewPressConfig"):
        orc.draft(topic="Topic")


def test_draft_builds_agents_from_config_when_pipeline_not_injected(tmp_path: Path) -> None:
    from brewpress.config import BrewPressConfig
    config = BrewPressConfig(google_api_key="fake-key")
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.writer_agent.WriterAgent") as MockWriter, \
         patch("brewpress.structurer_agent.StructurerAgent") as MockStructurer, \
         patch("brewpress.seo_agent.SEOAgent") as MockSEO, \
         patch("brewpress.critic_agent.CriticAgent") as MockCritic, \
         patch("brewpress.orchestrator.ingest") as mock_ingest:

        writer_inst = MagicMock()
        writer_inst.generate.return_value = _job()
        MockWriter.return_value = writer_inst

        structurer_inst = MagicMock()
        structurer_inst.structure.side_effect = lambda j: j
        MockStructurer.return_value = structurer_inst

        seo_inst = MagicMock()
        seo_inst.optimize.side_effect = lambda j: j
        MockSEO.return_value = seo_inst

        critic_inst = MagicMock()
        critic_inst.review.return_value = _pass_result()
        MockCritic.return_value = critic_inst

        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        Orchestrator(store=store).draft(topic="Topic", config=config)

    MockWriter.assert_called_once_with(config)
    MockStructurer.assert_called_once_with(config)
    MockSEO.assert_called_once_with(config)
    MockCritic.assert_called_once_with(config)


def test_draft_propagates_writer_value_error(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    pipeline.writer.generate.side_effect = ValueError("multi-topic without force")
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        with pytest.raises(ValueError, match="multi-topic"):
            Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")


# ------------------------------------------------------------------ #
# Orchestrator.draft() — revision loop                                 #
# ------------------------------------------------------------------ #


def test_draft_pass_first_attempt_pipeline_summary_one_round(tmp_path: Path) -> None:
    pipeline = _make_pipeline(critic_results=[_pass_result()])
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert "1 round" in result.pipeline_summary
    assert "seo:" in result.pipeline_summary
    assert result.job.state == JobState.REVIEWED


def test_draft_revise_then_pass_loops_correctly(tmp_path: Path) -> None:
    """Critic revises on attempt 1, passes on attempt 2."""
    pipeline = _make_pipeline(
        critic_results=[_revise_result("fix hook"), _pass_result()]
    )
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert pipeline.critic.review.call_count == 2
    assert pipeline.writer.generate_revision.call_count == 1
    assert "2 rounds" in result.pipeline_summary
    assert result.job.state == JobState.REVIEWED


def test_draft_max_revisions_rejects_job(tmp_path: Path) -> None:
    """After 3 revise verdicts, job is REJECTED with max_revisions_exceeded."""
    pipeline = _make_pipeline(
        critic_results=[
            _revise_result("fix hook"),
            _revise_result("fix clarity"),
            _revise_result("still broken"),
        ]
    )
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert result.job.state == JobState.REJECTED
    assert result.job.rejected_reason == "max_revisions_exceeded"
    assert pipeline.critic.review.call_count == 3
    assert result.pipeline_summary == ""


def test_draft_revise_instruction_propagated_to_next_writer_call(tmp_path: Path) -> None:
    """revision_instruction from critic is stored in job.revise_instruction for next pass."""
    instruction = "Rewrite the intro to open with the problem, not a definition."
    revise_job = _job()

    # Track what job is passed to generate_revision
    captured_jobs: list[BlogJob] = []

    def capture_revision(job: BlogJob, ctx) -> BlogJob:
        captured_jobs.append(job)
        return _job()  # return a fresh job for the second pass

    pipeline = _make_pipeline(critic_results=[_revise_result(instruction), _pass_result()])
    pipeline.writer.generate_revision.side_effect = capture_revision
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert len(captured_jobs) == 1
    assert captured_jobs[0].revise_instruction == instruction
    assert captured_jobs[0].revision_attempt == 1


def test_draft_auto_approve_rejects_when_max_revisions(tmp_path: Path) -> None:
    """auto_approve=True does not override a max_revisions_exceeded rejection."""
    pipeline = _make_pipeline(
        critic_results=[_revise_result(), _revise_result(), _revise_result()]
    )
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="Topic", auto_approve=True
        )

    assert result.job.state == JobState.REJECTED


# ------------------------------------------------------------------ #
# is_code_post tagging                                                 #
# ------------------------------------------------------------------ #


def test_draft_tags_is_code_post_true_when_context_is_code_post(tmp_path: Path) -> None:
    draft_job = _job()
    pipeline = _make_pipeline(draft_job=draft_job)
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

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="", diff_path="fake.diff"
        )

    assert result.job.is_code_post is True


def test_draft_tags_is_code_post_false_for_regular_post(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(topic="Topic")

    assert result.job.is_code_post is False


# ------------------------------------------------------------------ #
# auto_approve                                                         #
# ------------------------------------------------------------------ #


def test_draft_auto_approve_returns_approved_step_1(tmp_path: Path) -> None:
    pipeline = _make_pipeline(draft_job=_job(quality_score=80))
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="Topic", auto_approve=True
        )

    assert result.job.state == JobState.APPROVED_STEP_1


def test_draft_without_auto_approve_returns_reviewed(tmp_path: Path) -> None:
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        result = Orchestrator(store=store, pipeline=pipeline).draft(
            topic="Topic", auto_approve=False
        )

    assert result.job.state == JobState.REVIEWED


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
    published = approved.model_copy(update={"wp_post_id": 42})
    wp.publish.return_value = published

    orc = Orchestrator(store=store, wp_client=wp)
    orc.publish()

    saved = store.load()
    assert saved.wp_post_id == 42


def test_publish_calls_wp_client_with_job(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 99})

    orc = Orchestrator(store=store, wp_client=wp)
    orc.publish()

    call_kwargs = wp.publish.call_args
    passed_job = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1]["job"]
    assert passed_job.job_id == approved.job_id


def test_publish_builds_client_from_config_when_not_injected(tmp_path: Path) -> None:
    from brewpress.config import BrewPressConfig
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)
    config = BrewPressConfig(
        wp_url="https://example.com",
        wp_username="admin",
        wp_app_password="pass",
    )

    with patch("brewpress.orchestrator.WordPressClient") as MockWP:
        mock_client = MagicMock()
        mock_client.publish.return_value = approved.model_copy(update={"wp_post_id": 1})
        MockWP.return_value = mock_client

        orc = Orchestrator(store=store)
        orc.publish(config=config)

    MockWP.assert_called_once_with(config)


def test_publish_raises_if_no_draft_exists(tmp_path: Path) -> None:
    store = StateStore(path=tmp_path / "last_draft.json")  # empty store
    orc = Orchestrator(store=store)

    with pytest.raises(FileNotFoundError):
        orc.publish()


def test_publish_raises_if_wrong_state(tmp_path: Path) -> None:
    reviewed = _reviewed_job()
    store = _make_store(job=reviewed, tmp_path=tmp_path)

    orc = Orchestrator(store=store, wp_client=MagicMock())
    with pytest.raises(ValueError, match="approved_step_2"):
        orc.publish()


def test_publish_raises_if_no_client_and_no_config(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    orc = Orchestrator(store=store)  # no wp_client, no config
    with pytest.raises(ValueError, match="wp_client"):
        orc.publish()


def test_publish_writes_failure_bundle_on_publish_error(tmp_path: Path) -> None:
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = MagicMock()
    wp.publish.side_effect = PublishError("WP API error")

    bundle_dir = tmp_path / "bundles"
    orc = Orchestrator(store=store, wp_client=wp)

    with pytest.raises(PublishError):
        orc.publish(bundle_dir=bundle_dir)

    bundle_files = list(bundle_dir.glob("failure_bundle_*.json"))
    assert len(bundle_files) == 1


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
    """publish() must not invoke any pipeline agents."""
    approved = _approved_step2_job()
    store = _make_store(job=approved, tmp_path=tmp_path)

    pipeline = _make_pipeline()
    wp = MagicMock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, pipeline=pipeline, wp_client=wp)
    orc.publish()

    pipeline.writer.generate.assert_not_called()
    pipeline.critic.review.assert_not_called()


def test_no_wp_calls_in_draft(tmp_path: Path) -> None:
    """draft() must not call WordPressClient.publish()."""
    pipeline = _make_pipeline()
    store = _make_store(tmp_path=tmp_path)
    wp = MagicMock()

    with patch("brewpress.orchestrator.ingest") as mock_ingest:
        ctx = MagicMock()
        ctx.is_code_post = False
        ctx.commands = []
        mock_ingest.return_value = ctx

        Orchestrator(store=store, pipeline=pipeline, wp_client=wp).draft(topic="Topic")

    wp.publish.assert_not_called()


# ------------------------------------------------------------------ #
# Publish hookups: body sanitizer + hero-image picker                #
# ------------------------------------------------------------------ #


def _wp_mock() -> MagicMock:
    """Return a MagicMock spec'd against WordPressClient so signature drift fails fast."""
    from brewpress.wp_client import WordPressClient
    return MagicMock(spec=WordPressClient)


def test_publish_strips_scaffolding_from_body_before_wp_call(tmp_path: Path) -> None:
    """Orchestrator must call sanitize_body_for_publish before WP.publish."""
    body_with_scaffolding = (
        "# Title\n\n"
        "Reader intro.\n\n"
        "## Executed Tutorial Steps\n\n"
        "```json\n[{\"step_id\": \"01\"}]\n```\n\n"
        "## Real Section\n\nReader content.\n"
    )
    approved = _approved_step2_job(draft_body_md=body_with_scaffolding)
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = _wp_mock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, wp_client=wp)
    orc.publish()

    args, kwargs = wp.publish.call_args
    passed_job = args[0] if args else kwargs["job"]
    assert "Executed Tutorial Steps" not in passed_job.draft_body_md
    assert "step_id" not in passed_job.draft_body_md
    assert "## Real Section" in passed_job.draft_body_md
    assert "Reader content." in passed_job.draft_body_md


def test_publish_clean_body_skips_body_model_copy(tmp_path: Path) -> None:
    """No scaffolding -> sanitize_body_for_publish called once and returns
    original; orchestrator skips the body-update model_copy branch (proven by
    the body identity check on the job that reaches wp.publish)."""
    clean = "# Title\n\n## Step 1\n\nReader content only.\n"
    approved = _approved_step2_job(draft_body_md=clean)
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = _wp_mock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    # Stub sanitizer with identity. If orchestrator unconditionally model_copy'd
    # the job, draft_body_md would still be `clean` (so we can't catch that here),
    # but we DO assert the sanitizer was called exactly once with the unchanged body.
    with patch("brewpress.publish_sanitizer.sanitize_body_for_publish",
               side_effect=lambda body: body) as spy:
        orc = Orchestrator(store=store, wp_client=wp)
        orc.publish()
        spy.assert_called_once_with(clean)

    args, kwargs = wp.publish.call_args
    passed_job = args[0] if args else kwargs["job"]
    assert passed_job.draft_body_md == clean


def test_publish_dirty_body_triggers_model_copy(tmp_path: Path) -> None:
    """Stub the sanitizer to return a different body; orchestrator must
    pass that new body to wp.publish (proves the conditional model_copy
    branch fires when sanitizer changes content)."""
    original_body = "# Title\n\n## Some Section\n\nbody\n"
    sanitized = "# Title\n\n## Some Section\n\nNEW BODY\n"
    approved = _approved_step2_job(draft_body_md=original_body)
    store = _make_store(job=approved, tmp_path=tmp_path)

    wp = _wp_mock()
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    with patch("brewpress.publish_sanitizer.sanitize_body_for_publish",
               return_value=sanitized) as spy:
        orc = Orchestrator(store=store, wp_client=wp)
        orc.publish()
        spy.assert_called_once_with(original_body)

    args, kwargs = wp.publish.call_args
    passed_job = args[0] if args else kwargs["job"]
    assert passed_job.draft_body_md == sanitized


def test_publish_prefers_output_screenshot_as_hero(tmp_path: Path) -> None:
    """When media dir has both output_*.png and terminal_*.png, output wins."""
    approved = _approved_step2_job(is_code_post=True)
    store = _make_store(job=approved, tmp_path=tmp_path)

    media_dir = tmp_path / "media" / approved.job_id
    media_dir.mkdir(parents=True)
    (media_dir / "terminal_2026-05-04_cmd_aaaa1111.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (media_dir / "output_2026-05-04_cmd_aaaa1111.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from brewpress.wp_client import UploadedMedia
    wp = _wp_mock()
    wp.upload_image_file.return_value = UploadedMedia(
        id=777, url="https://example.com/output.webp", filename="output.png",
    )
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, wp_client=wp, media_base=tmp_path / "media")
    orc.publish()

    uploaded_path = wp.upload_image_file.call_args[0][0]
    assert uploaded_path.name.startswith("output_"), (
        f"Expected output_*.png as hero, got {uploaded_path.name}"
    )
    _, kwargs = wp.publish.call_args
    assert kwargs.get("featured_media_id") == 777


def test_publish_falls_back_to_terminal_when_no_output_image(tmp_path: Path) -> None:
    """Only terminal_*.png present → use it as hero."""
    approved = _approved_step2_job(is_code_post=True)
    store = _make_store(job=approved, tmp_path=tmp_path)

    media_dir = tmp_path / "media" / approved.job_id
    media_dir.mkdir(parents=True)
    (media_dir / "terminal_2026-05-04_cmd_bbbb2222.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from brewpress.wp_client import UploadedMedia
    wp = _wp_mock()
    wp.upload_image_file.return_value = UploadedMedia(
        id=888, url="https://example.com/terminal.webp", filename="terminal.png",
    )
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, wp_client=wp, media_base=tmp_path / "media")
    orc.publish()

    uploaded_path = wp.upload_image_file.call_args[0][0]
    assert uploaded_path.name.startswith("terminal_")


def test_publish_falls_back_to_terminal_when_output_upload_fails(tmp_path: Path) -> None:
    """If output upload raises PublishError, retry with terminal — never publish without a hero
    when both candidates exist."""
    approved = _approved_step2_job(is_code_post=True)
    store = _make_store(job=approved, tmp_path=tmp_path)

    media_dir = tmp_path / "media" / approved.job_id
    media_dir.mkdir(parents=True)
    (media_dir / "output_2026-05-04_cmd_aaaa1111.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (media_dir / "terminal_2026-05-04_cmd_aaaa1111.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from brewpress.wp_client import UploadedMedia
    wp = _wp_mock()
    # First call (output) fails; second call (terminal) succeeds.
    wp.upload_image_file.side_effect = [
        PublishError("output upload failed"),
        UploadedMedia(id=999, url="https://example.com/terminal.webp", filename="terminal.png"),
    ]
    wp.publish.return_value = approved.model_copy(update={"wp_post_id": 1})

    orc = Orchestrator(store=store, wp_client=wp, media_base=tmp_path / "media")
    orc.publish()

    assert wp.upload_image_file.call_count == 2, "Expected fallback retry"
    first_path = wp.upload_image_file.call_args_list[0][0][0]
    second_path = wp.upload_image_file.call_args_list[1][0][0]
    assert first_path.name.startswith("output_")
    assert second_path.name.startswith("terminal_")
    _, kwargs = wp.publish.call_args
    assert kwargs.get("featured_media_id") == 999
