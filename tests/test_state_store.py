"""Tests for brewpress.state_store — StateStore persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brewpress.models import BlogJob, JobState
from brewpress.state_store import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    """StateStore backed by a temp directory — never touches ~/.brewpress."""
    return StateStore(path=tmp_path / "last_draft.json")


# ------------------------------------------------------------------ #
# save                                                                 #
# ------------------------------------------------------------------ #


def test_save_creates_file(store: StateStore) -> None:
    job = BlogJob()
    store.save(job)
    assert store.path.exists()


def test_save_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "last_draft.json"
    s = StateStore(path=nested)
    s.save(BlogJob())
    assert nested.exists()


def test_save_writes_valid_json(store: StateStore) -> None:
    store.save(BlogJob())
    data = json.loads(store.path.read_text())
    assert "job_id" in data
    assert data["schema_version"] == 1


def test_save_overwrites_previous(store: StateStore) -> None:
    first = BlogJob()
    store.save(first)
    second = BlogJob()
    store.save(second)
    data = json.loads(store.path.read_text())
    assert data["job_id"] == second.job_id


def test_save_is_atomic_no_partial_file(store: StateStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """If rename succeeds, file content is complete (not partial)."""
    job = BlogJob(title="Atomic test")
    store.save(job)
    loaded = store.load()
    assert loaded.title == "Atomic test"


# ------------------------------------------------------------------ #
# load                                                                 #
# ------------------------------------------------------------------ #


def test_load_round_trip(store: StateStore) -> None:
    job = BlogJob(title="Hello", slug="hello")
    store.save(job)
    loaded = store.load()
    assert loaded == job


def test_load_preserves_state(store: StateStore) -> None:
    job = BlogJob().mark_reviewed().approve_content()
    store.save(job)
    loaded = store.load()
    assert loaded.state == JobState.APPROVED_STEP_1
    assert loaded.content_approved_at == job.content_approved_at


def test_load_preserves_wp_post_id(store: StateStore) -> None:
    job = BlogJob()
    # Simulate wp_post_id being set after publish
    enriched = job.model_copy(update={"wp_post_id": 42})
    store.save(enriched)
    loaded = store.load()
    assert loaded.wp_post_id == 42


def test_load_file_not_found(store: StateStore) -> None:
    with pytest.raises(FileNotFoundError, match="brewpress draft"):
        store.load()


def test_load_malformed_json(store: StateStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        store.load()


def test_load_wrong_schema_version(store: StateStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    data = BlogJob().to_json()
    data["schema_version"] = 99
    store.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="schema version"):
        store.load()


def test_load_corrupt_but_valid_json(store: StateStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('{"schema_version": 1, "state": "not_a_real_state"}', encoding="utf-8")
    with pytest.raises(ValueError, match="could not be parsed"):
        store.load()


# ------------------------------------------------------------------ #
# clear                                                                #
# ------------------------------------------------------------------ #


def test_clear_removes_file(store: StateStore) -> None:
    store.save(BlogJob())
    store.clear()
    assert not store.path.exists()


def test_clear_is_idempotent(store: StateStore) -> None:
    store.clear()  # file never existed
    store.clear()  # second call: no exception


def test_clear_then_load_raises(store: StateStore) -> None:
    store.save(BlogJob())
    store.clear()
    with pytest.raises(FileNotFoundError):
        store.load()


# ------------------------------------------------------------------ #
# path configuration                                                   #
# ------------------------------------------------------------------ #


def test_custom_path_respected(tmp_path: Path) -> None:
    custom = tmp_path / "custom.json"
    s = StateStore(path=custom)
    s.save(BlogJob())
    assert custom.exists()


def test_default_path_is_home_brewpress(monkeypatch: pytest.MonkeyPatch) -> None:
    from brewpress.state_store import _DEFAULT_STATE_FILE
    assert str(_DEFAULT_STATE_FILE).endswith(".brewpress/last_draft.json")
