"""Tests for brewpress.execution_layer — command execution, trace, and logging."""

from __future__ import annotations

from brewpress.execution_layer import (
    CommandResult,
    ExecutionTrace,
    _strip_prompt,
    run_command,
    run_commands,
)

# ------------------------------------------------------------------ #
# _strip_prompt                                                        #
# ------------------------------------------------------------------ #


def test_strip_prompt_removes_dollar_prefix() -> None:
    assert _strip_prompt("$ echo hello") == "echo hello"


def test_strip_prompt_no_prefix_unchanged() -> None:
    assert _strip_prompt("echo hello") == "echo hello"


def test_strip_prompt_trims_whitespace() -> None:
    assert _strip_prompt("  $ echo hi  ") == "echo hi"


def test_strip_prompt_ignores_bare_dollar() -> None:
    assert _strip_prompt("$echo") == "$echo"  # no space after $


# ------------------------------------------------------------------ #
# run_command — successful execution                                   #
# ------------------------------------------------------------------ #


def test_run_command_exit_code_zero_on_success() -> None:
    result = run_command("echo hello")
    assert result.exit_code == 0


def test_run_command_stdout_captured() -> None:
    result = run_command("echo hello")
    assert "hello" in result.stdout


def test_run_command_preserves_original_command_string() -> None:
    result = run_command("$ echo hi")
    assert result.command == "$ echo hi"


def test_run_command_strips_prompt_when_running() -> None:
    # '$ echo hello' should run as 'echo hello' and produce output
    result = run_command("$ echo hello")
    assert "hello" in result.stdout


def test_run_command_stderr_captured() -> None:
    result = run_command("echo err >&2")
    assert "err" in result.stderr


def test_run_command_duration_ms_positive() -> None:
    result = run_command("echo hi")
    assert result.duration_ms >= 0


def test_run_command_ran_at_is_iso8601() -> None:
    result = run_command("echo hi")
    assert "T" in result.ran_at  # ISO 8601 contains 'T'


def test_run_command_returns_command_result() -> None:
    assert isinstance(run_command("echo hi"), CommandResult)


# ------------------------------------------------------------------ #
# run_command — failure                                                #
# ------------------------------------------------------------------ #


def test_run_command_exit_code_nonzero_on_failure() -> None:
    result = run_command("exit 1")
    assert result.exit_code != 0


def test_run_command_nonexistent_binary_nonzero() -> None:
    result = run_command("__brewpress_nonexistent_binary_xyz__")
    assert result.exit_code != 0


# ------------------------------------------------------------------ #
# ExecutionTrace                                                       #
# ------------------------------------------------------------------ #


def test_execution_trace_succeeded_all_pass() -> None:
    results = [
        CommandResult("echo a", "a\n", "", 0, 10, "2024-01-01T00:00:00+00:00"),
        CommandResult("echo b", "b\n", "", 0, 10, "2024-01-01T00:00:00+00:00"),
    ]
    trace = ExecutionTrace(job_id="j1", results=results, completed_at="2024-01-01T00:00:01+00:00")
    assert trace.succeeded is True


def test_execution_trace_succeeded_false_on_failure() -> None:
    results = [
        CommandResult("echo a", "a\n", "", 0, 10, "2024-01-01T00:00:00+00:00"),
        CommandResult("exit 1", "", "", 1, 5, "2024-01-01T00:00:00+00:00"),
    ]
    trace = ExecutionTrace(job_id="j1", results=results, completed_at="")
    assert trace.succeeded is False


def test_execution_trace_succeeded_false_when_empty() -> None:
    trace = ExecutionTrace(job_id="j1", results=[])
    assert trace.succeeded is False


def test_execution_trace_failed_commands() -> None:
    fail = CommandResult("bad", "", "err", 1, 5, "2024-01-01T00:00:00+00:00")
    ok = CommandResult("echo hi", "hi\n", "", 0, 5, "2024-01-01T00:00:00+00:00")
    trace = ExecutionTrace(job_id="j1", results=[ok, fail])
    assert trace.failed_commands == [fail]


def test_execution_trace_failed_commands_empty_on_success() -> None:
    ok = CommandResult("echo hi", "hi\n", "", 0, 5, "2024-01-01T00:00:00+00:00")
    trace = ExecutionTrace(job_id="j1", results=[ok])
    assert trace.failed_commands == []


# ------------------------------------------------------------------ #
# run_commands                                                         #
# ------------------------------------------------------------------ #


def test_run_commands_returns_execution_trace() -> None:
    trace = run_commands(["echo a", "echo b"])
    assert isinstance(trace, ExecutionTrace)


def test_run_commands_all_succeed() -> None:
    trace = run_commands(["echo a", "echo b", "echo c"])
    assert len(trace.results) == 3
    assert trace.succeeded is True


def test_run_commands_stops_on_first_failure() -> None:
    trace = run_commands(["echo a", "exit 1", "echo c"])
    # 'echo c' must NOT have run
    assert len(trace.results) == 2
    assert trace.results[-1].exit_code != 0


def test_run_commands_partial_trace_available() -> None:
    trace = run_commands(["echo first", "exit 1", "echo never"])
    assert "first" in trace.results[0].stdout


def test_run_commands_empty_list_returns_empty_trace() -> None:
    trace = run_commands([])
    assert trace.results == []
    assert trace.succeeded is False


def test_run_commands_embeds_job_id() -> None:
    trace = run_commands(["echo hi"], job_id="test-job-42")
    assert trace.job_id == "test-job-42"


def test_run_commands_completed_at_set() -> None:
    trace = run_commands(["echo hi"])
    assert "T" in trace.completed_at
