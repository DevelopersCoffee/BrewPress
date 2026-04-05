"""Execution Layer — run host commands with full visible trace.

All commands are logged before execution. No command runs silently.
The ExecutionTrace is the contract between this layer and the Media Agent:
every captured screenshot must be backed by a real CommandResult in the trace.

PRD §Execution Layer constraints:
    - runs commands on host
    - logs all commands
    - stores execution trace
    - no hidden execution

run_commands() stops on the first non-zero exit code.  The partial trace
(all results up to and including the failure) is always returned so the
caller can decide how to surface the failure.

ADK integration note: run_command() maps cleanly to an ADK Tool call.
The CommandResult output is the grounding input for the Media Agent.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ------------------------------------------------------------------ #
# Data models                                                          #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class CommandResult:
    """Result of a single command execution."""

    command: str    # the original command string, as provided
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    ran_at: str     # ISO 8601 UTC timestamp


@dataclass(frozen=True)
class ExecutionTrace:
    """Ordered log of all commands run for one blog-generation job."""

    job_id: str
    results: list[CommandResult] = field(default_factory=list)
    completed_at: str = ""   # ISO 8601 UTC; set when run_commands() finishes

    @property
    def succeeded(self) -> bool:
        """True only when every command exited with code 0."""
        return bool(self.results) and all(r.exit_code == 0 for r in self.results)

    @property
    def failed_commands(self) -> list[CommandResult]:
        return [r for r in self.results if r.exit_code != 0]


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _strip_prompt(command: str) -> str:
    """Remove a leading '$ ' prompt marker if present (from user notes format)."""
    cmd = command.strip()
    return cmd[2:] if cmd.startswith("$ ") else cmd


# ------------------------------------------------------------------ #
# Core execution                                                       #
# ------------------------------------------------------------------ #


def run_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Execute a single shell command and return its full result.

    The command is run via the system shell (shell=True) so that
    shell built-ins, pipelines, and environment expansion work as
    the user expects from their notes.

    Args:
        command: Shell command string.  A leading '$ ' prompt is stripped.
        cwd:     Working directory for the subprocess.
        timeout: Seconds before the process is killed.
        env:     Optional environment override.  None inherits the parent env.

    Returns:
        CommandResult with stdout, stderr, exit_code, and duration_ms.

    Raises:
        subprocess.TimeoutExpired: Re-raised after the process is killed;
            stdout/stderr up to the timeout are lost.
    """
    clean = _strip_prompt(command)
    ran_at = datetime.now(UTC).isoformat()
    start = time.monotonic()

    proc = subprocess.run(
        clean,
        shell=True,  # noqa: S602 — commands come from user-controlled notes/diff
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        env=env,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    return CommandResult(
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        ran_at=ran_at,
    )


def run_commands(
    commands: list[str],
    *,
    cwd: str | None = None,
    timeout: int = 60,
    env: dict[str, str] | None = None,
    job_id: str = "",
) -> ExecutionTrace:
    """Execute commands in order, stopping on the first failure.

    Every command is run and recorded before the next one starts.
    The trace is always returned — even when a command fails — so
    the caller sees the full picture.

    Args:
        commands: Ordered list of shell command strings.
        cwd:      Working directory for all subprocesses.
        timeout:  Per-command timeout in seconds.
        env:      Optional environment override.
        job_id:   Optional job ID to embed in the trace.

    Returns:
        ExecutionTrace containing results for all executed commands.
        Stops after the first non-zero exit code.
    """
    results: list[CommandResult] = []

    for cmd in commands:
        result = run_command(cmd, cwd=cwd, timeout=timeout, env=env)
        results.append(result)
        if result.exit_code != 0:
            break  # visible stop — caller sees partial trace

    return ExecutionTrace(
        job_id=job_id,
        results=results,
        completed_at=datetime.now(UTC).isoformat(),
    )
