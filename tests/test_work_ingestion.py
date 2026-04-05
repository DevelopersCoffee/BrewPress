"""Tests for brewpress.work_ingestion — diff parsing, command extraction,
code-post detection, and end-to-end ingest()."""

from __future__ import annotations

import pytest

from brewpress.work_ingestion import (
    detect_code_post,
    extract_commands,
    ingest,
    parse_diff,
)

# ------------------------------------------------------------------ #
# Helpers / fixtures                                                   #
# ------------------------------------------------------------------ #

GIT_DIFF_SINGLE = """\
diff --git a/src/Foo.java b/src/Foo.java
index abc1234..def5678 100644
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -10,6 +10,8 @@ public class Foo {
     void existing() {}
-    void old() {}
+    void new1() {}
+    void new2() {}
 }
"""

GIT_DIFF_TWO_FILES = """\
diff --git a/src/Foo.java b/src/Foo.java
index abc..def 100644
--- a/src/Foo.java
+++ b/src/Foo.java
@@ -1,3 +1,4 @@
-old foo
+new foo
+extra foo
 context
diff --git a/src/Bar.java b/src/Bar.java
index 111..222 100644
--- a/src/Bar.java
+++ b/src/Bar.java
@@ -5,4 +5,3 @@
 context
-old bar
 context
"""

PLAIN_UNIFIED_DIFF = """\
--- foo.py
+++ foo.py
@@ -1,3 +1,4 @@
 context
-removed line
+added line
+second added
"""

DIFF_WITH_COMMANDS = """\
diff --git a/README.md b/README.md
index 000..111 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,4 @@
 # Project
+$ mvn clean install
+$ ./run_tests.sh
"""


# ------------------------------------------------------------------ #
# parse_diff — empty input                                             #
# ------------------------------------------------------------------ #


def test_parse_diff_empty_string() -> None:
    result = parse_diff("")
    assert result.hunks == []
    assert result.files_changed == []
    assert result.raw == ""


def test_parse_diff_whitespace_only() -> None:
    result = parse_diff("   \n\n")
    assert result.hunks == []
    assert result.files_changed == []


# ------------------------------------------------------------------ #
# parse_diff — single file, git format                                 #
# ------------------------------------------------------------------ #


def test_parse_diff_single_file_hunk_count() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    assert len(result.hunks) == 1


def test_parse_diff_single_file_file_path() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    assert result.hunks[0].file_path == "src/Foo.java"


def test_parse_diff_single_file_added_lines() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    hunk = result.hunks[0]
    assert "    void new1() {}" in hunk.added
    assert "    void new2() {}" in hunk.added


def test_parse_diff_single_file_removed_lines() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    hunk = result.hunks[0]
    assert "    void old() {}" in hunk.removed


def test_parse_diff_single_file_header_preserved() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    assert result.hunks[0].header.startswith("@@")


def test_parse_diff_preserves_raw() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    assert result.raw == GIT_DIFF_SINGLE


def test_parse_diff_files_changed_single() -> None:
    result = parse_diff(GIT_DIFF_SINGLE)
    assert result.files_changed == ["src/Foo.java"]


# ------------------------------------------------------------------ #
# parse_diff — multiple files                                          #
# ------------------------------------------------------------------ #


def test_parse_diff_two_files_hunk_count() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    assert len(result.hunks) == 2


def test_parse_diff_two_files_changed_order() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    assert result.files_changed == ["src/Foo.java", "src/Bar.java"]


def test_parse_diff_two_files_first_hunk_file() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    assert result.hunks[0].file_path == "src/Foo.java"


def test_parse_diff_two_files_second_hunk_file() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    assert result.hunks[1].file_path == "src/Bar.java"


def test_parse_diff_files_changed_no_duplicates() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    assert len(result.files_changed) == len(set(result.files_changed))


def test_parse_diff_two_files_added_content() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    foo_hunk = next(h for h in result.hunks if h.file_path == "src/Foo.java")
    assert "new foo" in foo_hunk.added
    assert "extra foo" in foo_hunk.added


def test_parse_diff_two_files_removed_content() -> None:
    result = parse_diff(GIT_DIFF_TWO_FILES)
    bar_hunk = next(h for h in result.hunks if h.file_path == "src/Bar.java")
    assert "old bar" in bar_hunk.removed


# ------------------------------------------------------------------ #
# parse_diff — plain unified diff (no "diff --git" header)            #
# ------------------------------------------------------------------ #


def test_parse_diff_plain_unified_hunk_count() -> None:
    result = parse_diff(PLAIN_UNIFIED_DIFF)
    assert len(result.hunks) == 1


def test_parse_diff_plain_unified_file_path() -> None:
    result = parse_diff(PLAIN_UNIFIED_DIFF)
    assert result.hunks[0].file_path == "foo.py"


def test_parse_diff_plain_unified_added() -> None:
    result = parse_diff(PLAIN_UNIFIED_DIFF)
    assert "added line" in result.hunks[0].added
    assert "second added" in result.hunks[0].added


def test_parse_diff_plain_unified_removed() -> None:
    result = parse_diff(PLAIN_UNIFIED_DIFF)
    assert "removed line" in result.hunks[0].removed


def test_parse_diff_context_lines_not_in_added_or_removed() -> None:
    result = parse_diff(PLAIN_UNIFIED_DIFF)
    hunk = result.hunks[0]
    assert not any("context" in line for line in hunk.added)
    assert not any("context" in line for line in hunk.removed)


# ------------------------------------------------------------------ #
# extract_commands                                                     #
# ------------------------------------------------------------------ #


def test_extract_commands_empty_notes() -> None:
    assert extract_commands("") == []


def test_extract_commands_no_prompt_lines() -> None:
    notes = "Just some prose without any commands.\nAnother line."
    assert extract_commands(notes) == []


def test_extract_commands_single_prompt_line() -> None:
    notes = "Run the build:\n$ mvn clean install\nDone."
    assert extract_commands(notes) == ["mvn clean install"]


def test_extract_commands_multiple_prompt_lines() -> None:
    notes = "$ ./gradlew test\n$ docker build -t app ."
    cmds = extract_commands(notes)
    assert "gradlew test" in cmds[0] or "./gradlew test" in cmds[0]
    assert len(cmds) == 2


def test_extract_commands_deduplication() -> None:
    notes = "$ npm install\n$ npm install"
    cmds = extract_commands(notes)
    assert cmds.count("npm install") == 1


def test_extract_commands_from_diff_added_lines() -> None:
    diff = parse_diff(DIFF_WITH_COMMANDS)
    cmds = extract_commands("", diff)
    assert "mvn clean install" in cmds
    assert "./run_tests.sh" in cmds


def test_extract_commands_dedup_across_notes_and_diff() -> None:
    diff = parse_diff(DIFF_WITH_COMMANDS)
    notes = "$ mvn clean install"  # same as in diff
    cmds = extract_commands(notes, diff)
    assert cmds.count("mvn clean install") == 1


def test_extract_commands_order_notes_before_diff() -> None:
    diff = parse_diff(DIFF_WITH_COMMANDS)
    notes = "$ echo hello"
    cmds = extract_commands(notes, diff)
    assert cmds[0] == "echo hello"


def test_extract_commands_indented_prompt() -> None:
    notes = "   $ pip install -r requirements.txt"
    cmds = extract_commands(notes)
    assert "pip install -r requirements.txt" in cmds


# ------------------------------------------------------------------ #
# detect_code_post                                                     #
# ------------------------------------------------------------------ #


def test_detect_code_post_diff_with_hunks() -> None:
    diff = parse_diff(GIT_DIFF_SINGLE)
    assert detect_code_post(diff, None, []) is True


def test_detect_code_post_empty_diff_no_hunks() -> None:
    diff = parse_diff("")
    assert detect_code_post(diff, None, []) is False


def test_detect_code_post_none_diff() -> None:
    assert detect_code_post(None, None, []) is False


def test_detect_code_post_pr_url_present() -> None:
    assert detect_code_post(None, "https://github.com/org/repo/pull/1", []) is True


def test_detect_code_post_commands_present() -> None:
    assert detect_code_post(None, None, ["./run.sh"]) is True


def test_detect_code_post_all_false() -> None:
    assert detect_code_post(None, None, []) is False


def test_detect_code_post_pr_url_empty_string() -> None:
    assert detect_code_post(None, "", []) is False


# ------------------------------------------------------------------ #
# ingest — idea post (topic only)                                      #
# ------------------------------------------------------------------ #


def test_ingest_topic_only_is_idea_post() -> None:
    ctx = ingest(topic="Java 21 virtual threads")
    assert ctx.is_code_post is False


def test_ingest_topic_only_no_diff() -> None:
    ctx = ingest(topic="system design")
    assert ctx.diff is None


def test_ingest_topic_only_no_commands() -> None:
    ctx = ingest(topic="AI agents in Java")
    assert ctx.commands == []


def test_ingest_strips_topic_whitespace() -> None:
    ctx = ingest(topic="  spring boot  ")
    assert ctx.topic == "spring boot"


def test_ingest_strips_notes_whitespace() -> None:
    ctx = ingest(topic="foo", notes="  bar  ")
    assert ctx.notes == "bar"


# ------------------------------------------------------------------ #
# ingest — with notes containing commands                              #
# ------------------------------------------------------------------ #


def test_ingest_notes_with_command_is_code_post() -> None:
    ctx = ingest(topic="CI pipeline", notes="$ mvn clean install")
    assert ctx.is_code_post is True


def test_ingest_notes_commands_extracted() -> None:
    ctx = ingest(topic="foo", notes="$ ./gradlew test")
    assert "./gradlew test" in ctx.commands


# ------------------------------------------------------------------ #
# ingest — with diff file                                              #
# ------------------------------------------------------------------ #


def test_ingest_with_diff_file_is_code_post(tmp_path: pytest.TempPathFactory) -> None:
    diff_file = tmp_path / "changes.diff"
    diff_file.write_text(GIT_DIFF_SINGLE, encoding="utf-8")
    ctx = ingest(topic="Refactor Foo", diff_path=str(diff_file))
    assert ctx.is_code_post is True


def test_ingest_with_diff_file_parsed(tmp_path: pytest.TempPathFactory) -> None:
    diff_file = tmp_path / "changes.diff"
    diff_file.write_text(GIT_DIFF_SINGLE, encoding="utf-8")
    ctx = ingest(topic="Refactor Foo", diff_path=str(diff_file))
    assert ctx.diff is not None
    assert len(ctx.diff.hunks) == 1


def test_ingest_with_diff_extracts_commands(tmp_path: pytest.TempPathFactory) -> None:
    diff_file = tmp_path / "changes.diff"
    diff_file.write_text(DIFF_WITH_COMMANDS, encoding="utf-8")
    ctx = ingest(topic="Update README", diff_path=str(diff_file))
    assert "mvn clean install" in ctx.commands


def test_ingest_diff_not_found_raises(tmp_path: pytest.TempPathFactory) -> None:
    with pytest.raises(FileNotFoundError):
        ingest(topic="foo", diff_path=str(tmp_path / "does_not_exist.diff"))


# ------------------------------------------------------------------ #
# ingest — with PR URL                                                 #
# ------------------------------------------------------------------ #


def test_ingest_pr_url_is_code_post() -> None:
    ctx = ingest(topic="Spring PR", pr_url="https://github.com/org/repo/pull/42")
    assert ctx.is_code_post is True


def test_ingest_pr_url_stored() -> None:
    url = "https://github.com/org/repo/pull/42"
    ctx = ingest(topic="Spring PR", pr_url=url)
    assert ctx.pr_url == url


def test_ingest_no_pr_url_is_none() -> None:
    ctx = ingest(topic="something")
    assert ctx.pr_url is None


# ------------------------------------------------------------------ #
# WorkContext is immutable                                             #
# ------------------------------------------------------------------ #


def test_work_context_is_frozen() -> None:
    ctx = ingest(topic="Java")
    with pytest.raises(Exception):
        ctx.topic = "mutated"  # type: ignore[misc]
