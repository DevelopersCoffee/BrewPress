"""Tests for brewpress.media_agent — screenshot rendering, capture,
manifest generation, and code-post validation."""

from __future__ import annotations

from pathlib import Path

from brewpress.execution_layer import CommandResult, ExecutionTrace
from brewpress.media_agent import (
    MediaManifest,
    MediaType,
    capture_screenshot,
    generate_for_code_post,
    render_terminal_image,
    validate_code_post_media,
)

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _is_png(data: bytes) -> bool:
    return data[:8] == _PNG_MAGIC


def _result(
    command: str = "mvn clean install",
    stdout: str = "BUILD SUCCESS\n",
    stderr: str = "",
    exit_code: int = 0,
) -> CommandResult:
    return CommandResult(
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=1200,
        ran_at="2024-06-01T12:00:00+00:00",
    )


def _trace(results: list[CommandResult] | None = None, job_id: str = "job-1") -> ExecutionTrace:
    return ExecutionTrace(
        job_id=job_id,
        results=results if results is not None else [_result()],
        completed_at="2024-06-01T12:00:01+00:00",
    )


# ------------------------------------------------------------------ #
# render_terminal_image                                                #
# ------------------------------------------------------------------ #


def test_render_returns_bytes() -> None:
    assert isinstance(render_terminal_image(["echo hello"]), bytes)


def test_render_returns_valid_png() -> None:
    data = render_terminal_image(["echo hello"])
    assert _is_png(data)


def test_render_empty_lines_returns_png() -> None:
    data = render_terminal_image([])
    assert _is_png(data)


def test_render_with_title() -> None:
    data = render_terminal_image(["output line"], title="Terminal")
    assert _is_png(data)


def test_render_with_stderr_lines() -> None:
    data = render_terminal_image(["stdout"], stderr_lines=["error!"])
    assert _is_png(data)


def test_render_many_lines_truncates() -> None:
    lines = [f"line {i}" for i in range(200)]
    data = render_terminal_image(lines)
    assert _is_png(data)
    # Should not fail even with many lines


def test_render_long_line_truncated() -> None:
    long_line = "x" * 500
    data = render_terminal_image([long_line])
    assert _is_png(data)


def test_render_prompt_line_does_not_raise() -> None:
    data = render_terminal_image(["$ mvn clean install"])
    assert _is_png(data)


# ------------------------------------------------------------------ #
# capture_screenshot — terminal                                        #
# ------------------------------------------------------------------ #


def test_capture_terminal_creates_file(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    assert item.path.exists()


def test_capture_terminal_is_png(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    assert _is_png(item.path.read_bytes())


def test_capture_terminal_media_type(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    assert item.media_type == MediaType.TERMINAL_SCREENSHOT


def test_capture_terminal_caption_contains_command(tmp_path: Path) -> None:
    item = capture_screenshot(_result(command="mvn test"), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    assert "mvn test" in item.caption


def test_capture_terminal_command_preserved(tmp_path: Path) -> None:
    result = _result(command="$ ./run.sh")
    item = capture_screenshot(result, tmp_path, MediaType.TERMINAL_SCREENSHOT)
    assert item.command == "$ ./run.sh"


def test_capture_terminal_creates_parent_dir(tmp_path: Path) -> None:
    sub = tmp_path / "nested" / "media"
    item = capture_screenshot(_result(), sub, MediaType.TERMINAL_SCREENSHOT)
    assert item.path.exists()


# ------------------------------------------------------------------ #
# capture_screenshot — output proof                                   #
# ------------------------------------------------------------------ #


def test_capture_output_creates_file(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    assert item.path.exists()


def test_capture_output_is_png(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    assert _is_png(item.path.read_bytes())


def test_capture_output_media_type(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    assert item.media_type == MediaType.OUTPUT_PROOF


def test_capture_output_different_file_from_terminal(tmp_path: Path) -> None:
    t = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    o = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    assert t.path != o.path


def test_capture_output_with_stderr_does_not_raise(tmp_path: Path) -> None:
    result = _result(stderr="ERROR: something failed")
    item = capture_screenshot(result, tmp_path, MediaType.OUTPUT_PROOF)
    assert item.path.exists()


# ------------------------------------------------------------------ #
# MediaManifest                                                        #
# ------------------------------------------------------------------ #


def test_manifest_has_terminal_screenshot_true(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    manifest = MediaManifest(job_id="j1", items=[item])
    assert manifest.has_terminal_screenshot is True


def test_manifest_has_terminal_screenshot_false() -> None:
    manifest = MediaManifest(job_id="j1", items=[])
    assert manifest.has_terminal_screenshot is False


def test_manifest_has_output_proof_true(tmp_path: Path) -> None:
    item = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    manifest = MediaManifest(job_id="j1", items=[item])
    assert manifest.has_output_proof is True


def test_manifest_has_output_proof_false() -> None:
    manifest = MediaManifest(job_id="j1", items=[])
    assert manifest.has_output_proof is False


def test_manifest_by_type(tmp_path: Path) -> None:
    t = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    o = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    manifest = MediaManifest(job_id="j1", items=[t, o])
    assert manifest.by_type(MediaType.TERMINAL_SCREENSHOT) == [t]
    assert manifest.by_type(MediaType.OUTPUT_PROOF) == [o]


# ------------------------------------------------------------------ #
# generate_for_code_post                                               #
# ------------------------------------------------------------------ #


def test_generate_creates_two_items(tmp_path: Path) -> None:
    manifest = generate_for_code_post("job-1", _trace(), tmp_path)
    assert len(manifest.items) == 2


def test_generate_has_terminal_screenshot(tmp_path: Path) -> None:
    manifest = generate_for_code_post("job-1", _trace(), tmp_path)
    assert manifest.has_terminal_screenshot


def test_generate_has_output_proof(tmp_path: Path) -> None:
    manifest = generate_for_code_post("job-1", _trace(), tmp_path)
    assert manifest.has_output_proof


def test_generate_embeds_job_id(tmp_path: Path) -> None:
    manifest = generate_for_code_post("test-job-99", _trace(), tmp_path)
    assert manifest.job_id == "test-job-99"


def test_generate_empty_trace_returns_empty_manifest(tmp_path: Path) -> None:
    trace = ExecutionTrace(job_id="j1", results=[], completed_at="")
    manifest = generate_for_code_post("j1", trace, tmp_path)
    assert manifest.items == []


def test_generate_prefers_successful_result(tmp_path: Path) -> None:
    fail = _result(command="bad cmd", exit_code=1, stdout="")
    ok = _result(command="mvn test", exit_code=0, stdout="BUILD SUCCESS\n")
    trace = ExecutionTrace(job_id="j1", results=[fail, ok], completed_at="")
    manifest = generate_for_code_post("j1", trace, tmp_path)
    assert all("mvn test" in item.command for item in manifest.items)


def test_generate_falls_back_to_first_on_all_failures(tmp_path: Path) -> None:
    fail1 = _result(command="cmd1", exit_code=1)
    fail2 = _result(command="cmd2", exit_code=2)
    trace = ExecutionTrace(job_id="j1", results=[fail1, fail2], completed_at="")
    manifest = generate_for_code_post("j1", trace, tmp_path)
    # Should still produce screenshots from the first result
    assert len(manifest.items) == 2
    assert all("cmd1" in item.command for item in manifest.items)


def test_generate_writes_png_files(tmp_path: Path) -> None:
    manifest = generate_for_code_post("j1", _trace(), tmp_path)
    for item in manifest.items:
        assert item.path.exists()
        assert _is_png(item.path.read_bytes())


# ------------------------------------------------------------------ #
# validate_code_post_media                                             #
# ------------------------------------------------------------------ #


def test_validate_passes_with_full_manifest(tmp_path: Path) -> None:
    manifest = generate_for_code_post("j1", _trace(), tmp_path)
    assert validate_code_post_media(manifest) == []


def test_validate_fails_empty_manifest() -> None:
    gaps = validate_code_post_media(MediaManifest(job_id="j1", items=[]))
    assert len(gaps) == 2


def test_validate_missing_terminal_screenshot(tmp_path: Path) -> None:
    o = capture_screenshot(_result(), tmp_path, MediaType.OUTPUT_PROOF)
    manifest = MediaManifest(job_id="j1", items=[o])
    gaps = validate_code_post_media(manifest)
    assert any("terminal" in g.lower() for g in gaps)
    assert not any("output" in g.lower() for g in gaps)


def test_validate_missing_output_proof(tmp_path: Path) -> None:
    t = capture_screenshot(_result(), tmp_path, MediaType.TERMINAL_SCREENSHOT)
    manifest = MediaManifest(job_id="j1", items=[t])
    gaps = validate_code_post_media(manifest)
    assert any("output" in g.lower() for g in gaps)
    assert not any("terminal" in g.lower() for g in gaps)


def test_validate_returns_list_of_strings() -> None:
    manifest = MediaManifest(job_id="j1", items=[])
    gaps = validate_code_post_media(manifest)
    assert all(isinstance(g, str) for g in gaps)
