"""Persistent state store for the active BrewPress job.

State is kept in a single JSON file at ~/.brewpress/last_draft.json.
Only one job is active at a time. All writes are atomic (write to a
temp file then os.rename) to prevent corrupt state on process kill.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from brewpress.models import BlogJob


_DEFAULT_STATE_DIR = Path.home() / ".brewpress"
_DEFAULT_STATE_FILE = _DEFAULT_STATE_DIR / "last_draft.json"


class StateStore:
    """Read and write the active BlogJob to disk."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_STATE_FILE

    @property
    def path(self) -> Path:
        return self._path

    def save(self, job: BlogJob) -> None:
        """Write job to disk atomically.

        Creates the parent directory if it does not exist.
        Uses a temp file + os.rename for atomic replacement.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(job.to_json(), indent=2, ensure_ascii=False)

        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent, prefix=".last_draft_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.rename(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load(self) -> BlogJob:
        """Load the active job from disk.

        Raises:
            FileNotFoundError: If no draft exists.
            ValueError: If the state file contains invalid JSON or an
                        unrecognised schema version.
        """
        if not self._path.exists():
            raise FileNotFoundError(
                f"No approved draft found at {self._path}. "
                "Run 'brewpress draft' first."
            )
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"State file at {self._path} contains invalid JSON: {exc}"
            ) from exc

        version = data.get("schema_version", 1)
        if version != 1:
            raise ValueError(
                f"State file uses schema version {version}, "
                "but this version of BrewPress only supports version 1. "
                "Run 'brewpress draft' to create a fresh draft."
            )

        try:
            return BlogJob.from_json(data)
        except Exception as exc:
            raise ValueError(
                f"State file at {self._path} could not be parsed: {exc}"
            ) from exc

    def clear(self) -> None:
        """Remove the state file. No-op if it does not exist."""
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
