# ADK Blog-Aware Header Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ADK-driven workflow that generates a blog-aware header image from a Markdown draft, uploads it to WordPress, and sets it as the draft post's featured image without publishing live.

**Architecture:** Keep side effects in deterministic Python tools and let an ADK workflow agent orchestrate them in sequence: parse blog context, plan prompt, generate image, write manifest, upload to WordPress, update draft featured media, and verify draft status. The CLI should call the ADK workflow path, not bypass it with a standalone helper.

**Tech Stack:** Python 3.11, Google ADK, OpenAI Images API through `requests`, existing `WordPressClient`, dataclasses, `pytest`, existing BrewPress environment/config conventions.

---

## File Structure

- Create `src/brewpress/header_image.py`
  - Data models, markdown parser, deterministic planner, OpenAI generator interface, manifest writing, WordPress attachment helpers.
- Create `src/brewpress/header_image_adk.py`
  - ADK workflow factory and agent instructions. Lazy-imports `google-adk`.
- Modify `src/brewpress/config.py`
  - Load optional `OPENAI_API_KEY` and `BREWPRESS_HEADER_IMAGE_MODEL`.
- Modify `src/brewpress/cli.py`
  - Add `generate-header-image` command that runs the ADK workflow path.
- Modify `.env.example`
  - Document `OPENAI_API_KEY` and `BREWPRESS_HEADER_IMAGE_MODEL`.
- Modify `README.md`
  - Document ADK header-image generation usage.
- Create `tests/test_header_image.py`
  - Deterministic tool tests with fakes.
- Create `tests/test_header_image_adk.py`
  - ADK factory tests with mocked ADK imports.
- Modify `tests/test_cli.py`
  - Parser and CLI command tests.

## Task 1: Add Header Image Data Models And Blog Context Tool

**Files:**
- Create: `src/brewpress/header_image.py`
- Test: `tests/test_header_image.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_header_image.py`:

```python
"""Tests for ADK blog-aware header image tools."""

from __future__ import annotations

import json
from pathlib import Path

from brewpress.header_image import (
    HeaderImageManifest,
    parse_markdown_draft,
    parse_markdown_draft_tool,
)


_DRAFT = """\
---
title: "Git Worktree for AI Coding Agents: An End-to-End Workflow"
slug: "git-worktree-ai-agents"
meta_description: "Use git worktree to isolate AI coding agents."
primary_keyword: "git worktree"
---

# Git Worktree for AI Coding Agents: An End-to-End Workflow

AI coding agents are fast, but they are not careful by default.

## The Real Insight

Git branches isolate history. Git worktrees isolate execution environments.

## Step 1: Create Worktrees

Use one worktree per agent task.
"""


def test_parse_markdown_draft_extracts_blog_context() -> None:
    parsed = parse_markdown_draft(_DRAFT)

    assert parsed.title == "Git Worktree for AI Coding Agents: An End-to-End Workflow"
    assert parsed.slug == "git-worktree-ai-agents"
    assert parsed.meta_description == "Use git worktree to isolate AI coding agents."
    assert parsed.primary_keyword == "git worktree"
    assert "The Real Insight" in parsed.headings
    assert "AI coding agents are fast" in parsed.intro_excerpt


def test_parse_markdown_draft_tool_returns_json_serializable_context(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.md"
    draft_path.write_text(_DRAFT, encoding="utf-8")

    result = parse_markdown_draft_tool(str(draft_path))

    assert result["status"] == "success"
    assert result["context"]["slug"] == "git-worktree-ai-agents"
    assert "Git Worktree" in result["context"]["title"]


def test_header_image_manifest_round_trips_to_json(tmp_path: Path) -> None:
    image_path = tmp_path / "header.png"
    image_path.write_bytes(b"fake png")
    manifest = HeaderImageManifest(
        blog_slug="git-worktree-ai-agents",
        title="Git Worktree for AI Coding Agents",
        prompt="Create a technical editorial image.",
        alt_text="Git worktree isolation for AI coding agents",
        caption="AI agents working in isolated git worktrees.",
        model="gpt-image-1",
        local_path=image_path,
        mime_type="image/png",
        generated_at="2026-05-04T00:00:00+00:00",
    )

    data = json.loads(manifest.to_json())

    assert data["blog_slug"] == "git-worktree-ai-agents"
    assert data["local_path"] == str(image_path)
    assert data["model"] == "gpt-image-1"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'brewpress.header_image'
```

- [ ] **Step 3: Implement minimal models and parser tool**

Create `src/brewpress/header_image.py`:

```python
"""ADK tools for blog-aware header image generation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedDraft:
    title: str
    slug: str
    meta_description: str
    primary_keyword: str
    headings: list[str]
    intro_excerpt: str
    body: str

    def to_tool_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HeaderImageBrief:
    blog_slug: str
    title: str
    visual_brief: str
    prompt: str
    alt_text: str
    caption: str
    style_tags: list[str]
    avoid_list: list[str]

    def to_tool_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HeaderImageManifest:
    blog_slug: str
    title: str
    prompt: str
    alt_text: str
    caption: str
    model: str
    local_path: Path
    mime_type: str
    generated_at: str

    def to_json(self) -> str:
        data = asdict(self)
        data["local_path"] = str(self.local_path)
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_tool_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["local_path"] = str(self.local_path)
        return data


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    frontmatter: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith("  - "):
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"')
    return frontmatter, raw[match.end():].lstrip()


def _intro_excerpt(body: str, max_chars: int = 360) -> str:
    paragraphs = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith("```")
    ]
    excerpt = " ".join(paragraphs)
    return excerpt[:max_chars].strip()


def parse_markdown_draft(raw: str) -> ParsedDraft:
    frontmatter, body = _parse_frontmatter(raw)
    headings = [item.strip() for item in _HEADING_RE.findall(body)]
    title = frontmatter.get("title") or (headings[0] if headings else "")
    return ParsedDraft(
        title=title,
        slug=frontmatter.get("slug", ""),
        meta_description=frontmatter.get("meta_description", ""),
        primary_keyword=frontmatter.get("primary_keyword", ""),
        headings=headings,
        intro_excerpt=_intro_excerpt(body),
        body=body,
    )


def parse_markdown_draft_tool(path: str) -> dict[str, object]:
    """ADK tool: read a Markdown draft and return blog context."""
    draft_path = Path(path)
    if not draft_path.is_file():
        return {"status": "error", "error": f"Draft not found: {draft_path}"}
    parsed = parse_markdown_draft(draft_path.read_text(encoding="utf-8"))
    return {"status": "success", "context": parsed.to_tool_dict()}
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py -q
```

Expected:

```text
...
```

- [ ] **Step 5: Commit**

```bash
git add src/brewpress/header_image.py tests/test_header_image.py
git commit -m "feat(media): add ADK header image context tool"
```

## Task 2: Add Blog-Aware Planning Tool

**Files:**
- Modify: `src/brewpress/header_image.py`
- Test: `tests/test_header_image.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_header_image.py`:

```python
from brewpress.header_image import plan_header_image, plan_header_image_tool


def test_plan_header_image_includes_blog_core_concepts() -> None:
    parsed = parse_markdown_draft(_DRAFT)

    brief = plan_header_image(parsed, site_name="Developers Coffee")

    assert brief.blog_slug == "git-worktree-ai-agents"
    assert "AI coding agents" in brief.visual_brief
    assert "isolated" in brief.prompt.lower()
    assert "git worktree" in brief.prompt.lower()
    assert "Developers Coffee" in brief.prompt


def test_plan_header_image_tool_returns_prompt_alt_text_and_caption() -> None:
    parsed = parse_markdown_draft(_DRAFT)

    result = plan_header_image_tool(parsed.to_tool_dict(), site_name="Developers Coffee")

    assert result["status"] == "success"
    assert "prompt" in result["brief"]
    assert result["brief"]["alt_text"]
    assert result["brief"]["caption"]
    assert result["brief"]["avoid_list"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py::test_plan_header_image_includes_blog_core_concepts tests/test_header_image.py::test_plan_header_image_tool_returns_prompt_alt_text_and_caption -q
```

Expected:

```text
ImportError: cannot import name 'plan_header_image'
```

- [ ] **Step 3: Implement planner and tool**

Append to `src/brewpress/header_image.py`:

```python
def _draft_from_tool_context(context: dict[str, object]) -> ParsedDraft:
    return ParsedDraft(
        title=str(context.get("title", "")),
        slug=str(context.get("slug", "")),
        meta_description=str(context.get("meta_description", "")),
        primary_keyword=str(context.get("primary_keyword", "")),
        headings=[str(item) for item in context.get("headings", [])],
        intro_excerpt=str(context.get("intro_excerpt", "")),
        body=str(context.get("body", "")),
    )


def plan_header_image(
    draft: ParsedDraft,
    *,
    site_name: str = "Developers Coffee",
) -> HeaderImageBrief:
    concepts = ", ".join(
        item
        for item in [
            draft.primary_keyword,
            "AI coding agents" if "AI coding agents" in draft.body else "",
            "isolated Git worktrees" if "worktree" in draft.body.lower() else "",
            "clean developer workflow",
        ]
        if item
    )
    visual_brief = (
        f"{concepts}. Technical editorial hero image for {site_name}, "
        "showing separate workspaces and branch isolation."
    )
    prompt = (
        "Create a modern technical blog header image. "
        f"Site: {site_name}. "
        f"Topic: {draft.title}. "
        f"Visual brief: {visual_brief} "
        "Show one central repository branching into three isolated developer workspaces: "
        "main review, AI agent docs, and AI agent tests. "
        "Use subtle terminal panels, git branch lines, warm coffee-colored highlights, "
        "and a clean editorial style. "
        "No brand logos, no readable code text, no fake UI claims, no cartoon robots."
    )
    title = draft.title or "Technical blog header"
    return HeaderImageBrief(
        blog_slug=draft.slug,
        title=title,
        visual_brief=visual_brief,
        prompt=prompt,
        alt_text=f"AI coding agents working in isolated git worktrees for {title}",
        caption="AI agents working in separate git worktree directories for cleaner reviews.",
        style_tags=[
            "technical editorial",
            "developer workflow",
            "warm coffee accents",
            "minimal text",
            "WordPress hero",
        ],
        avoid_list=[
            "third-party logos",
            "readable fake code",
            "cartoon robots",
            "stock-photo office scene",
            "unrelated coffee cup hero",
        ],
    )


def plan_header_image_tool(
    context: dict[str, object],
    site_name: str = "Developers Coffee",
) -> dict[str, object]:
    """ADK tool: create a post-specific visual prompt from blog context."""
    draft = _draft_from_tool_context(context)
    brief = plan_header_image(draft, site_name=site_name)
    return {"status": "success", "brief": brief.to_tool_dict()}
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py -q
```

Expected:

```text
.....
```

- [ ] **Step 5: Commit**

```bash
git add src/brewpress/header_image.py tests/test_header_image.py
git commit -m "feat(media): add ADK header image planner tool"
```

## Task 3: Add Image Generation And Manifest Tools

**Files:**
- Modify: `src/brewpress/header_image.py`
- Modify: `src/brewpress/config.py`
- Modify: `.env.example`
- Test: `tests/test_header_image.py`

- [ ] **Step 1: Write failing tests with fake generator**

Append to `tests/test_header_image.py`:

```python
from brewpress.header_image import (
    FakeHeaderImageGenerator,
    OpenAIHeaderImageGenerator,
    generate_header_image_tool,
)


def test_generate_header_image_tool_writes_image_and_manifest(tmp_path: Path) -> None:
    parsed = parse_markdown_draft(_DRAFT)
    brief = plan_header_image(parsed)

    result = generate_header_image_tool(
        brief.to_tool_dict(),
        output_dir=str(tmp_path),
        generator=FakeHeaderImageGenerator(),
    )

    assert result["status"] == "success"
    assert Path(result["manifest"]["local_path"]).exists()
    assert Path(result["manifest_path"]).exists()
    assert result["manifest"]["model"] == "fake-image-model"


def test_generate_header_image_tool_rejects_missing_output(tmp_path: Path) -> None:
    class BrokenGenerator:
        model = "broken"

        def generate(self, brief, output_dir):
            return output_dir / "missing.png"

    parsed = parse_markdown_draft(_DRAFT)
    brief = plan_header_image(parsed)

    result = generate_header_image_tool(
        brief.to_tool_dict(),
        output_dir=str(tmp_path),
        generator=BrokenGenerator(),
    )

    assert result["status"] == "error"
    assert "missing.png" in result["error"]


def test_openai_header_image_generator_requires_api_key() -> None:
    try:
        OpenAIHeaderImageGenerator(api_key="")
    except ValueError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py::test_generate_header_image_tool_writes_image_and_manifest tests/test_header_image.py::test_openai_header_image_generator_requires_api_key -q
```

Expected:

```text
ImportError
```

- [ ] **Step 3: Add config fields**

Modify `src/brewpress/config.py`:

```python
_ALL_VARS: tuple[str, ...] = (
    "WP_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
)
```

Add `openai_api_key` and `header_image_model` to `BrewPressConfig`, then return them from `load_config()`:

```python
openai_api_key: str | None = None
header_image_model: str = "gpt-image-1"
```

```python
openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip() or None,
header_image_model=os.environ.get("BREWPRESS_HEADER_IMAGE_MODEL", "").strip() or "gpt-image-1",
```

- [ ] **Step 4: Implement generator tools**

Append to `src/brewpress/header_image.py`:

```python
import base64
from datetime import UTC, datetime
from typing import Protocol

import requests


class HeaderImageGenerator(Protocol):
    model: str

    def generate(self, brief: HeaderImageBrief, output_dir: Path) -> Path:
        """Generate a local image file."""


class FakeHeaderImageGenerator:
    model = "fake-image-model"

    def generate(self, brief: HeaderImageBrief, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{brief.blog_slug}-header.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return path


class OpenAIHeaderImageGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-image-1",
        size: str = "1536x1024",
        timeout: int = 120,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required for header image generation.")
        self._api_key = api_key
        self.model = model
        self._size = size
        self._timeout = timeout

    def generate(self, brief: HeaderImageBrief, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "prompt": brief.prompt,
                "size": self._size,
                "n": 1,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        encoded = data["data"][0].get("b64_json")
        if not encoded:
            raise RuntimeError("OpenAI image response did not include b64_json.")
        path = output_dir / f"{brief.blog_slug}-header.png"
        path.write_bytes(base64.b64decode(encoded))
        return path


def _brief_from_tool_dict(data: dict[str, object]) -> HeaderImageBrief:
    return HeaderImageBrief(
        blog_slug=str(data.get("blog_slug", "")),
        title=str(data.get("title", "")),
        visual_brief=str(data.get("visual_brief", "")),
        prompt=str(data.get("prompt", "")),
        alt_text=str(data.get("alt_text", "")),
        caption=str(data.get("caption", "")),
        style_tags=[str(item) for item in data.get("style_tags", [])],
        avoid_list=[str(item) for item in data.get("avoid_list", [])],
    )


def _mime_type_for(path: Path) -> str:
    if path.suffix.lower() == ".webp":
        return "image/webp"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/png"


def generate_header_image_tool(
    brief: dict[str, object],
    output_dir: str,
    *,
    generator: HeaderImageGenerator | None = None,
    openai_api_key: str = "",
    model: str = "gpt-image-1",
) -> dict[str, object]:
    """ADK tool: generate image and write manifest."""
    output_path = Path(output_dir)
    resolved_brief = _brief_from_tool_dict(brief)
    resolved_generator = generator or OpenAIHeaderImageGenerator(
        api_key=openai_api_key,
        model=model,
    )
    try:
        image_path = resolved_generator.generate(resolved_brief, output_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Generated header image not found: {image_path}")
        if image_path.stat().st_size <= 0:
            raise ValueError(f"Generated header image is empty: {image_path}")
        manifest = HeaderImageManifest(
            blog_slug=resolved_brief.blog_slug,
            title=resolved_brief.title,
            prompt=resolved_brief.prompt,
            alt_text=resolved_brief.alt_text,
            caption=resolved_brief.caption,
            model=resolved_generator.model,
            local_path=image_path,
            mime_type=_mime_type_for(image_path),
            generated_at=datetime.now(UTC).isoformat(),
        )
        output_path.mkdir(parents=True, exist_ok=True)
        manifest_path = output_path / "header-image-manifest.json"
        manifest_path.write_text(manifest.to_json(), encoding="utf-8")
        return {
            "status": "success",
            "manifest": manifest.to_tool_dict(),
            "manifest_path": str(manifest_path),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
```

- [ ] **Step 5: Document env vars**

Append to `.env.example`:

```bash
# Optional: blog-aware header image generation
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
BREWPRESS_HEADER_IMAGE_MODEL=gpt-image-1
```

- [ ] **Step 6: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py tests/test_config.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 7: Commit**

```bash
git add src/brewpress/header_image.py src/brewpress/config.py .env.example tests/test_header_image.py
git commit -m "feat(media): add ADK header image generation tool"
```

## Task 4: Add WordPress Attachment And Verification Tools

**Files:**
- Modify: `src/brewpress/header_image.py`
- Test: `tests/test_header_image.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_header_image.py`:

```python
from brewpress.header_image import (
    attach_header_image_to_draft_tool,
    verify_wordpress_draft_tool,
)
from brewpress.wp_client import UploadedMedia


class FakeWordPressClient:
    def __init__(self) -> None:
        self.uploaded_path: Path | None = None
        self.featured_media_id = None

    def upload_image_file(self, path: Path) -> UploadedMedia:
        self.uploaded_path = path
        return UploadedMedia(id=123, url="https://example.com/header.png", filename=path.name)

    def publish(self, job, featured_media_id=None, gallery_media=None):
        self.featured_media_id = featured_media_id
        return job.model_copy(update={"wp_post_id": job.target_wp_post_id or 796})

    def _get(self, path: str, **params):
        return {
            "id": 796,
            "status": "draft",
            "slug": "git-worktree-ai-agents",
            "title": {"raw": "Git Worktree for AI Coding Agents"},
            "featured_media": 123,
        }


def test_attach_header_image_to_draft_tool_uploads_and_sets_featured_media(tmp_path: Path) -> None:
    image_path = tmp_path / "header.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    manifest = {
        "blog_slug": "git-worktree-ai-agents",
        "title": "Git Worktree for AI Coding Agents",
        "prompt": "prompt",
        "alt_text": "alt",
        "caption": "caption",
        "model": "fake",
        "local_path": str(image_path),
        "mime_type": "image/png",
        "generated_at": "2026-05-04T00:00:00+00:00",
    }
    client = FakeWordPressClient()

    result = attach_header_image_to_draft_tool(
        manifest=manifest,
        post_id=796,
        title="Git Worktree for AI Coding Agents",
        slug="git-worktree-ai-agents",
        body_md="# Git Worktree\n\nBody",
        meta_description="Use git worktree with AI agents.",
        client=client,
    )

    assert result["status"] == "success"
    assert result["media_id"] == 123
    assert result["post_id"] == 796
    assert client.uploaded_path == image_path
    assert client.featured_media_id == 123


def test_verify_wordpress_draft_tool_confirms_draft_and_featured_media() -> None:
    result = verify_wordpress_draft_tool(
        post_id=796,
        expected_slug="git-worktree-ai-agents",
        client=FakeWordPressClient(),
    )

    assert result["status"] == "success"
    assert result["post_status"] == "draft"
    assert result["featured_media"] == 123
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py::test_attach_header_image_to_draft_tool_uploads_and_sets_featured_media tests/test_header_image.py::test_verify_wordpress_draft_tool_confirms_draft_and_featured_media -q
```

Expected:

```text
ImportError
```

- [ ] **Step 3: Implement WordPress tools**

Append to `src/brewpress/header_image.py`:

```python
from brewpress.models import BlogJob, JobIntent


def attach_header_image_to_draft_tool(
    *,
    manifest: dict[str, object],
    post_id: int,
    title: str,
    slug: str,
    body_md: str,
    meta_description: str,
    client,
) -> dict[str, object]:
    """ADK tool: upload image and set featured media on a WordPress draft."""
    image_path = Path(str(manifest.get("local_path", "")))
    if not image_path.is_file():
        return {"status": "error", "error": f"Header image not found: {image_path}"}
    uploaded = client.upload_image_file(image_path)
    job = BlogJob(
        intent=JobIntent.UPDATE_POST,
        target_wp_post_id=post_id,
        title=title,
        slug=slug,
        meta_description=meta_description,
        excerpt=meta_description,
        draft_body_md=body_md,
        is_code_post=True,
        publish_live=False,
    )
    updated = client.publish(job, featured_media_id=uploaded.id)
    return {
        "status": "success",
        "media_id": uploaded.id,
        "media_url": uploaded.url,
        "post_id": updated.wp_post_id,
    }


def verify_wordpress_draft_tool(
    *,
    post_id: int,
    expected_slug: str,
    client,
) -> dict[str, object]:
    """ADK tool: verify post remains a draft and has featured media."""
    post = client._get(f"posts/{post_id}", context="edit")
    post_status = str(post.get("status", ""))
    slug = str(post.get("slug", ""))
    featured_media = int(post.get("featured_media") or 0)
    if post_status != "draft":
        return {"status": "error", "error": f"Expected draft status, got {post_status}"}
    if expected_slug and slug != expected_slug:
        return {"status": "error", "error": f"Expected slug {expected_slug}, got {slug}"}
    if featured_media <= 0:
        return {"status": "error", "error": "Featured media is not set."}
    return {
        "status": "success",
        "post_id": int(post.get("id", post_id)),
        "post_status": post_status,
        "slug": slug,
        "featured_media": featured_media,
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/brewpress/header_image.py tests/test_header_image.py
git commit -m "feat(media): add ADK WordPress header image tools"
```

## Task 5: Add ADK Workflow Factory

**Files:**
- Create: `src/brewpress/header_image_adk.py`
- Test: `tests/test_header_image_adk.py`

- [ ] **Step 1: Write failing ADK factory tests**

Create `tests/test_header_image_adk.py`:

```python
"""Tests for ADK header image workflow factory."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from brewpress.header_image_adk import create_header_image_workflow_agent


def test_create_header_image_workflow_agent_raises_without_adk() -> None:
    with patch.dict(sys.modules, {"google.adk.agents.llm_agent": None}):
        with pytest.raises(RuntimeError, match="google-adk"):
            create_header_image_workflow_agent(model="gemini-2.5-flash")


def test_create_header_image_workflow_agent_builds_root_agent_with_tools() -> None:
    fake_agent = MagicMock(side_effect=lambda **kwargs: {"agent": kwargs})
    fake_sequential = MagicMock(side_effect=lambda **kwargs: {"workflow": kwargs})

    with patch.dict(
        sys.modules,
        {
            "google.adk": MagicMock(),
            "google.adk.agents": MagicMock(),
            "google.adk.agents.llm_agent": MagicMock(Agent=fake_agent),
            "google.adk.agents.sequential_agent": MagicMock(SequentialAgent=fake_sequential),
        },
    ):
        workflow = create_header_image_workflow_agent(model="gemini-2.5-flash")

    assert "workflow" in workflow
    sub_agents = workflow["workflow"]["sub_agents"]
    assert len(sub_agents) == 4
    tool_counts = [len(agent["agent"].get("tools", [])) for agent in sub_agents]
    assert tool_counts == [1, 1, 1, 2]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image_adk.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'brewpress.header_image_adk'
```

- [ ] **Step 3: Implement ADK workflow factory**

Create `src/brewpress/header_image_adk.py`:

```python
"""ADK workflow factory for blog-aware header image generation."""

from __future__ import annotations

from brewpress.header_image import (
    attach_header_image_to_draft_tool,
    generate_header_image_tool,
    parse_markdown_draft_tool,
    plan_header_image_tool,
    verify_wordpress_draft_tool,
)


def create_header_image_workflow_agent(*, model: str = "gemini-2.5-flash"):
    """Create an ADK workflow agent for header image generation."""
    try:
        from google.adk.agents.llm_agent import Agent
        from google.adk.agents.sequential_agent import SequentialAgent
    except ImportError as exc:
        raise RuntimeError(
            "ADK header image workflow requires google-adk. Install the ADK extra "
            "before using this integration."
        ) from exc

    blog_context_agent = Agent(
        model=model,
        name="BlogContextAgent",
        instruction=(
            "Read the Markdown draft path from the user input and call "
            "parse_markdown_draft_tool. Return only the parsed context."
        ),
        tools=[parse_markdown_draft_tool],
        output_key="blog_context",
    )
    planner_agent = Agent(
        model=model,
        name="HeaderImagePlannerAgent",
        instruction=(
            "Use blog_context to call plan_header_image_tool. The image must be "
            "directly related to the post content and must avoid unrelated stock-art."
        ),
        tools=[plan_header_image_tool],
        output_key="header_image_brief",
    )
    generator_agent = Agent(
        model=model,
        name="HeaderImageGeneratorAgent",
        instruction=(
            "Use header_image_brief to call generate_header_image_tool. Return the "
            "manifest path and local image path."
        ),
        tools=[generate_header_image_tool],
        output_key="header_image_manifest",
    )
    publisher_agent = Agent(
        model=model,
        name="WordPressDraftPublisherAgent",
        instruction=(
            "Upload the generated header image, attach it as featured media to the "
            "requested WordPress draft, then verify the post remains draft."
        ),
        tools=[attach_header_image_to_draft_tool, verify_wordpress_draft_tool],
        output_key="wordpress_header_image_result",
    )
    return SequentialAgent(
        name="HeaderImageWorkflowAgent",
        sub_agents=[
            blog_context_agent,
            planner_agent,
            generator_agent,
            publisher_agent,
        ],
    )
```

- [ ] **Step 4: Run ADK factory tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image_adk.py -q
```

Expected:

```text
..
```

- [ ] **Step 5: Commit**

```bash
git add src/brewpress/header_image_adk.py tests/test_header_image_adk.py
git commit -m "feat(media): add ADK header image workflow"
```

## Task 6: Add CLI Command That Uses The ADK Workflow Path

**Files:**
- Modify: `src/brewpress/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write parser test**

Append to `tests/test_cli.py`:

```python
def test_generate_header_image_parser_args() -> None:
    parser = build_parser()

    args = parser.parse_args([
        "generate-header-image",
        "--draft-md",
        "docs/blog-drafts/post.md",
        "--wp-post-id",
        "796",
        "--output-dir",
        "artifacts/header",
    ])

    assert args.command == "generate-header-image"
    assert args.draft_md == "docs/blog-drafts/post.md"
    assert args.wp_post_id == 796
    assert args.output_dir == "artifacts/header"
```

- [ ] **Step 2: Run parser test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py::test_generate_header_image_parser_args -q
```

Expected:

```text
SystemExit: 2
```

- [ ] **Step 3: Add parser command**

Modify `src/brewpress/cli.py` in `build_parser()`:

```python
    header = sub.add_parser(
        "generate-header-image",
        help="Run the ADK workflow that generates and attaches a blog-aware header image.",
    )
    header.add_argument("--draft-md", required=True, help="Path to the Markdown draft.")
    header.add_argument("--wp-post-id", required=True, type=int, help="WordPress draft post ID.")
    header.add_argument(
        "--output-dir",
        default="artifacts/header-image",
        help="Directory for generated image and manifest.",
    )
```

- [ ] **Step 4: Add CLI execution using ADK workflow factory and deterministic tool runner**

Modify `src/brewpress/cli.py` in `main()` before the final `return 0`:

```python
    if args.command == "generate-header-image":
        from pathlib import Path as _Path

        from brewpress.config import load_config
        from brewpress.header_image import (
            attach_header_image_to_draft_tool,
            generate_header_image_tool,
            parse_markdown_draft_tool,
            plan_header_image_tool,
            verify_wordpress_draft_tool,
        )
        from brewpress.header_image_adk import create_header_image_workflow_agent
        from brewpress.wp_client import WordPressClient

        draft_path = _Path(args.draft_md)
        if not draft_path.is_file():
            print(f"[brewpress] draft not found: {draft_path}", file=sys.stderr)
            return 1

        try:
            config = load_config(required=("OPENAI_API_KEY", "WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"))
        except OSError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

        try:
            create_header_image_workflow_agent(model=config.header_image_model)
        except RuntimeError as exc:
            print(f"[brewpress] {exc}", file=sys.stderr)
            return 1

        context_result = parse_markdown_draft_tool(str(draft_path))
        if context_result["status"] != "success":
            print(f"[brewpress] {context_result['error']}", file=sys.stderr)
            return 1
        context = context_result["context"]
        brief_result = plan_header_image_tool(context, site_name=config.site_name)
        image_result = generate_header_image_tool(
            brief_result["brief"],
            output_dir=args.output_dir,
            openai_api_key=config.openai_api_key or "",
            model=config.header_image_model,
        )
        if image_result["status"] != "success":
            print(f"[brewpress] {image_result['error']}", file=sys.stderr)
            return 1
        client = WordPressClient(config)
        attach_result = attach_header_image_to_draft_tool(
            manifest=image_result["manifest"],
            post_id=args.wp_post_id,
            title=str(context["title"]),
            slug=str(context["slug"]),
            body_md=str(context["body"]),
            meta_description=str(context["meta_description"]),
            client=client,
        )
        if attach_result["status"] != "success":
            print(f"[brewpress] {attach_result['error']}", file=sys.stderr)
            return 1
        verify_result = verify_wordpress_draft_tool(
            post_id=args.wp_post_id,
            expected_slug=str(context["slug"]),
            client=client,
        )
        if verify_result["status"] != "success":
            print(f"[brewpress] {verify_result['error']}", file=sys.stderr)
            return 1
        print(f"[brewpress] ADK workflow configured: HeaderImageWorkflowAgent")
        print(f"[brewpress] Header image generated: {image_result['manifest']['local_path']}")
        print(f"[brewpress] Manifest written: {image_result['manifest_path']}")
        print(f"[brewpress] WordPress draft updated. Post ID: {verify_result['post_id']}")
        print(f"[brewpress] Featured media: {verify_result['featured_media']}")
        return 0
```

This CLI path creates the ADK workflow object and executes the same ADK tools deterministically in-process for MVP. A future ADK runner can invoke the same tools through an ADK session service without changing the tool boundaries.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli.py::test_generate_header_image_parser_args tests/test_cli.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit**

```bash
git add src/brewpress/cli.py tests/test_cli.py
git commit -m "feat(cli): add ADK header image command"
```

## Task 7: Add README Usage Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add usage section**

Add near WordPress publishing docs:

```markdown
### Generate a blog-aware header image with ADK

BrewPress can run an ADK workflow that generates a header image from a Markdown draft, uploads it to WordPress, and sets it as the draft's featured image:

```bash
brewpress generate-header-image \
  --draft-md docs/blog-drafts/2026-05-03-git-worktree-ai-agents.md \
  --wp-post-id 796 \
  --output-dir artifacts/header/git-worktree-ai-agents
```

Required environment variables:

```bash
OPENAI_API_KEY=...
WP_URL=https://www.example.com
WP_USERNAME=...
WP_APP_PASSWORD=...
```

The command keeps the post as a WordPress draft. It does not publish live.
```

- [ ] **Step 2: Run docs-adjacent tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_header_image.py tests/test_header_image_adk.py tests/test_cli.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(media): document ADK header image workflow"
```

## Task 8: Manual End-To-End Execution For Draft 796

**Files:**
- No source changes expected.
- Generated artifact path: `artifacts/header/git-worktree-ai-agents/`

- [ ] **Step 1: Verify environment without printing secrets**

Run:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import os
required = ["OPENAI_API_KEY", "WP_URL", "WP_USERNAME", "WP_APP_PASSWORD"]
missing = [name for name in required if not os.environ.get(name)]
print("missing=", missing)
PY
```

Expected:

```text
missing= []
```

If local credentials are only in `/Users/udaychauhan/workspace/developerscoffee.com/.env`, load them into the environment without printing values before running the command.

- [ ] **Step 2: Generate and attach the header image through the ADK workflow path**

Run:

```bash
PYTHONPATH=src .venv/bin/brewpress generate-header-image \
  --draft-md docs/blog-drafts/2026-05-03-git-worktree-ai-agents.md \
  --wp-post-id 796 \
  --output-dir artifacts/header/git-worktree-ai-agents
```

Expected:

```text
[brewpress] ADK workflow configured: HeaderImageWorkflowAgent
[brewpress] Header image generated: artifacts/header/git-worktree-ai-agents/git-worktree-ai-agents-header.png
[brewpress] Manifest written: artifacts/header/git-worktree-ai-agents/header-image-manifest.json
[brewpress] WordPress draft updated. Post ID: 796
[brewpress] Featured media: <non-zero generated image media id>
```

- [ ] **Step 3: Read back WordPress draft status**

Run a read-back script using `WordPressClient._get("posts/796", context="edit")`.

Expected:

```text
status=draft
slug=git-worktree-ai-agents
featured_media=<non-zero generated image media id>
```

- [ ] **Step 4: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Commit final integrated state**

```bash
git add src/brewpress/header_image.py src/brewpress/header_image_adk.py src/brewpress/config.py src/brewpress/cli.py .env.example README.md tests/test_header_image.py tests/test_header_image_adk.py tests/test_cli.py
git commit -m "feat(media): generate blog-aware header images with ADK"
```

## Self-Review Notes

- Spec coverage: ADK root workflow, blog context extraction, prompt planning, OpenAI generation, manifest writing, WordPress draft attachment, read-back verification, security, and manual draft `796` execution are covered.
- Scope: one reusable ADK workflow plus deterministic tools. Full ADK image editing, masked edits, and multi-turn image state management remain out of scope.
- Placeholder scan: no `TBD`, `TODO`, or unspecified "handle errors later" steps.
- Type consistency: `HeaderImageBrief`, `HeaderImageManifest`, `create_header_image_workflow_agent`, `parse_markdown_draft_tool`, `plan_header_image_tool`, `generate_header_image_tool`, `attach_header_image_to_draft_tool`, and `verify_wordpress_draft_tool` are introduced before use.
