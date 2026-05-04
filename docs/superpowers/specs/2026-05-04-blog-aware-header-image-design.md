# ADK Blog-Aware Header Image Generation Design

## Purpose

BrewPress should use an ADK agent workflow to generate a header image that is related to a blog post, upload it to WordPress, and set it as the draft post's featured image. The image must be derived from the post content, not from a fixed generic prompt.

The first target post is the Developers Coffee draft:

- Title: `Git Worktree for AI Coding Agents: An End-to-End Workflow`
- Slug: `git-worktree-ai-agents`
- WordPress draft ID: `796`

## Success Criteria

- An ADK root agent coordinates the end-to-end header image workflow.
- The workflow extracts blog context from the Markdown draft.
- The workflow creates a post-specific visual brief, prompt, alt text, and caption.
- The workflow generates a local image artifact with an OpenAI image model.
- The workflow writes a local manifest with prompt and image metadata.
- The workflow uploads the image to WordPress using the existing secure media upload path.
- The uploaded image is set as `featured_media` on the WordPress draft.
- The post remains a WordPress draft; no live publish happens.
- The implementation is reusable for future blog posts.

## Non-Goals

- Do not build a full ADK image editing workflow in this slice.
- Do not add multi-turn image state management.
- Do not add masked editing, segmentation, or image composition.
- Do not publish posts live.
- Do not generate unrelated decorative images.
- Do not store API keys or WordPress credentials in source, docs, tests, screenshots, generated prompts, or generated manifests.

## Architecture

Use ADK for orchestration and focused Python tools for side effects:

```text
HeaderImageWorkflowAgent
  -> BlogContextAgent
     -> parse_markdown_draft_tool
  -> HeaderImagePlannerAgent
     -> plan_header_image_tool
  -> HeaderImageGeneratorAgent
     -> generate_header_image_tool
     -> write_header_manifest_tool
  -> WordPressDraftPublisherAgent
     -> upload_header_image_tool
     -> update_wordpress_draft_featured_media_tool
     -> verify_wordpress_draft_tool
```

ADK owns the workflow and decision sequence. Tools own deterministic parsing, OpenAI image API calls, local artifact writes, and WordPress REST calls. This keeps the system agentic without letting the LLM handle credentials, raw HTTP details, or unsafe publishing decisions.

## Agent Responsibilities

### HeaderImageWorkflowAgent

The root ADK workflow agent. For MVP, this should be represented by a sequential ADK workflow where each sub-agent receives the prior output. The root workflow returns a structured final result with:

- generated local image path
- manifest path
- WordPress media ID
- WordPress post ID
- WordPress post status
- featured media read-back result

### BlogContextAgent

Extracts the post context from a Markdown draft by calling a deterministic tool.

Input:

- Markdown draft path

Output:

- title
- slug
- meta description
- primary keyword
- headings
- intro excerpt
- body markdown

### HeaderImagePlannerAgent

Creates the visual brief and prompt from the blog context.

Output:

- `visual_brief`
- `prompt`
- `alt_text`
- `caption`
- `style_tags`
- `avoid_list`

For the Git worktree post, the planner should produce a brief similar to:

> AI coding agents working in isolated Git worktrees, clean developer workflow, terminal/workspace diagram, Developers Coffee editorial style.

The prompt must avoid literal screenshots, third-party logos, fake UI claims, unreadable text-heavy images, and unrelated robot/coffee stock-art.

### HeaderImageGeneratorAgent

Calls image-generation tools and records the local artifact.

Input:

- prompt
- slug
- output directory
- configured image model

Output:

- local image path
- model
- MIME type
- manifest path

The first implementation should use an OpenAI image model such as `gpt-image-1` or the configured current image-generation model. The model must be configurable through environment variables so BrewPress can move to newer image models without code changes.

### WordPressDraftPublisherAgent

Uploads the generated image and attaches it to the WordPress draft.

Input:

- local image path
- draft WordPress post ID
- title
- slug
- body markdown
- meta description

Output:

- uploaded media ID
- updated WordPress post ID
- read-back status
- read-back featured media ID

This agent must never publish live. It updates draft posts only.

## Tool Boundaries

Tools should be normal Python functions so they can be called by ADK agents and tested directly.

Required tools:

- `parse_markdown_draft_tool(path: str) -> dict`
- `plan_header_image_tool(context: dict, site_name: str) -> dict`
- `generate_header_image_tool(brief: dict, output_dir: str, model: str) -> dict`
- `write_header_manifest_tool(result: dict, output_dir: str) -> dict`
- `attach_header_image_to_draft_tool(manifest: dict, post_id: int) -> dict`
- `verify_wordpress_draft_tool(post_id: int) -> dict`

The tools may share implementation helpers, but each tool should have a narrow responsibility and a JSON-serializable return shape.

## Data Flow

```text
docs/blog-drafts/2026-05-03-git-worktree-ai-agents.md
  -> BlogContextAgent
  -> HeaderImagePlannerAgent
  -> HeaderImageGeneratorAgent
  -> WordPressDraftPublisherAgent
  -> draft 796 read-back verification
```

## Image Style Guidance

Default visual direction:

- Technical editorial hero
- Clear isolation metaphor
- Git branches and separate workspaces
- AI agents represented abstractly, not as cartoon robots
- Dark terminal accents with warm Developers Coffee tones
- Minimal or no text inside the image
- WordPress-friendly hero aspect ratio

For the Git worktree article, a good image concept is:

> A clean editorial illustration showing one central repository branching into three isolated workspaces: main review, AI agent docs, and AI agent tests. Include subtle terminal panels, branch lines, and warm coffee-colored highlights. No brand logos. No readable code text. Modern technical blog hero image.

## Error Handling

- If blog parsing fails, stop before image generation.
- If image generation fails, keep the post draft unchanged and report the failure.
- If image upload fails, keep the local image artifact and manifest for retry.
- If WordPress update fails, leave the image artifact and manifest available for retry.
- If the generated image is missing or zero bytes, fail before upload.
- If credentials are missing, stop before generation/upload and report required environment variables.
- If read-back status is not `draft`, report a failure.

## Testing

Unit tests:

- Markdown parsing extracts title, slug, headings, intro excerpt, and metadata.
- Planner creates a prompt from a real blog post and includes core concepts.
- Planner does not produce empty alt text or caption.
- Generator tool validates missing API key without making network calls.
- Manifest serialization includes local path, prompt, model, and slug.
- WordPress attachment tool passes generated media ID as `featured_media`.

ADK workflow tests:

- `create_header_image_workflow_agent()` returns an ADK root workflow object when `google-adk` imports are available.
- Missing `google-adk` raises a clear runtime error.
- Tool list includes parse, plan, generate, attach, and verify tools.
- A fake/injected runner can execute the workflow without real OpenAI or WordPress calls.

Manual verification for the first post:

- Run the ADK header-image workflow against the Git worktree draft.
- Generate the header image from the blog content.
- Upload it to WordPress.
- Update draft post `796`.
- Read back post `796` and confirm:
  - status is `draft`
  - slug is `git-worktree-ai-agents`
  - title matches the article
  - featured media ID is set to the generated image

## Security

- Read OpenAI and WordPress credentials only from environment variables or ignored local `.env`.
- Never write credentials into manifests, markdown, screenshots, logs, generated prompts, or generated images.
- Do not include real user data, API keys, or private repository names in generated prompts.
- Keep prompt metadata safe for public repo storage.
- Keep WordPress updates draft-only unless a separate explicit live-publish command is approved.

## Implementation Slice

The first implementation should include:

1. Header-image data models and deterministic tools.
2. OpenAI image-generation tool behind a small interface.
3. WordPress draft attachment and verification tools.
4. ADK workflow factory that wires the tools into a root workflow agent.
5. CLI/manual command that runs the ADK workflow for a draft path and WordPress draft ID.
6. Tests with fake generator and fake WordPress client.
7. Manual execution against draft `796`.

This keeps the feature small enough to ship while making the end-to-end path agent-driven through ADK.
