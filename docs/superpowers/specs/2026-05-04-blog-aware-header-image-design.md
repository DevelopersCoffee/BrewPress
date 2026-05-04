# Blog-Aware Header Image Generation Design

## Purpose

BrewPress should generate a header image that is related to the blog post, upload it to WordPress, and set it as the draft post's featured image. The image should be derived from the post content, not from a fixed generic prompt.

The first target post is the Developers Coffee draft:

- Title: `Git Worktree for AI Coding Agents: An End-to-End Workflow`
- Slug: `git-worktree-ai-agents`
- WordPress draft ID: `796`

## Success Criteria

- A header image is generated from the blog post's title, metadata, headings, and core concepts.
- The generated image is saved as a local artifact with its prompt and metadata.
- The image is uploaded to WordPress using the existing media upload path.
- The uploaded image is set as `featured_media` on the WordPress draft.
- The post remains a WordPress draft; no live publish happens.
- The implementation is reusable for future blog posts.

## Non-Goals

- Do not build a full ADK image editing workflow in this slice.
- Do not add multi-turn image state management.
- Do not publish posts live.
- Do not generate unrelated decorative images.
- Do not store API keys or WordPress credentials in source, docs, tests, screenshots, or generated artifacts.

## Recommended Approach

Use a reusable BrewPress header-image pipeline:

```text
BlogJob / Markdown draft
  -> HeaderImagePlanner
  -> OpenAIHeaderImageGenerator
  -> HeaderImageManifest
  -> WordPress media upload
  -> WordPress draft featured_media update
```

This gives the fastest path to a working Developers Coffee draft while keeping the feature useful for later posts.

## Components

### HeaderImagePlanner

Input:

- Blog title
- Slug
- Meta description
- Primary keyword
- Key headings
- Short excerpt from the introduction
- Optional site identity: Developers Coffee, practical developer tone

Output:

- `visual_brief`
- `prompt`
- `alt_text`
- `caption`
- `style_tags`
- `avoid_list`

For the Git worktree post, the planner should produce a brief similar to:

> AI coding agents working in isolated Git worktrees, clean developer workflow, terminal/workspace diagram, Developers Coffee editorial style.

The planner should avoid literal screenshots, logos for third-party tools, fake UI claims, unreadable text-heavy images, and unrelated robot/coffee stock-art.

### OpenAIHeaderImageGenerator

Input:

- Planned prompt
- Output directory
- Desired format
- Desired dimensions

Output:

- Local image file
- Generation metadata

The first implementation should use an OpenAI image model such as `gpt-image-1` or the configured current image-generation model. The exact model should be configurable through environment variables so BrewPress can move to newer models without code changes.

### HeaderImageManifest

The manifest records:

- `blog_slug`
- `title`
- `prompt`
- `alt_text`
- `caption`
- `model`
- `local_path`
- `mime_type`
- `generated_at`

This is useful for debugging, repeatability, and failure bundles.

### WordPress Publisher Integration

The existing `WordPressClient.upload_image_file()` already supports local image upload and returns a WordPress media ID. The header-image feature should reuse that path.

Publishing flow:

1. Generate or locate the header image artifact.
2. Upload the image to WordPress media.
3. Publish/update the post as draft with `featured_media` set to the uploaded media ID.
4. Verify by reading back the post status, featured media ID, slug, and title.

## Data Flow

```text
docs/blog-drafts/2026-05-03-git-worktree-ai-agents.md
  -> parse frontmatter and markdown body
  -> extract title, description, headings, core concepts
  -> build HeaderImageBrief
  -> generate image artifact
  -> write HeaderImageManifest
  -> upload image to WordPress
  -> update draft ID 796 / slug git-worktree-ai-agents
```

## Image Style Guidance

Default visual direction:

- Technical editorial hero
- Clear isolation metaphor
- Git branches and separate workspaces
- AI agents represented abstractly, not as cartoon robots
- Dark terminal accents with warm Developers Coffee tones
- Minimal or no text inside the image
- 16:9 or WordPress-friendly hero aspect ratio

For the Git worktree article, a good image concept is:

> A clean editorial illustration showing one central repository branching into three isolated workspaces: main review, AI agent docs, and AI agent tests. Include subtle terminal panels, branch lines, and warm coffee-colored highlights. No brand logos. No readable code text. Modern technical blog hero image.

## Error Handling

- If image generation fails, keep the post draft unchanged and report the failure.
- If image upload fails, keep the local image artifact and report the upload error.
- If WordPress update fails, leave the image artifact and manifest available for retry.
- If the generated image is missing or zero bytes, fail before upload.
- If credentials are missing, stop before generation/upload and report required environment variables.

## Testing

Unit tests:

- Planner creates a prompt from a real blog post and includes core concepts.
- Planner does not produce an empty alt text or caption.
- Manifest serialization includes local path, prompt, model, and slug.
- Publisher path passes generated media ID as `featured_media`.

Integration-style tests with fakes:

- Fake image generator writes an image file.
- Fake WordPress client records upload and publish/update calls.
- End-to-end flow verifies the post stays in `draft` status.

Manual verification for the first post:

- Generate the header image from the Git worktree draft.
- Upload it to WordPress.
- Update draft post `796`.
- Read back post `796` and confirm:
  - status is `draft`
  - slug is `git-worktree-ai-agents`
  - title matches the article
  - featured media ID is set to the generated image

## Security

- Read OpenAI and WordPress credentials only from environment variables or ignored local `.env`.
- Never write credentials into manifests, markdown, screenshots, logs, or generated images.
- Do not include real user data, API keys, or private repository names in generated prompts.
- Keep prompt metadata safe for public repo storage.

## Implementation Slice

The first implementation should include:

1. `HeaderImageBrief` and `HeaderImageManifest` data models.
2. A deterministic planner that derives a visual brief from blog markdown.
3. An OpenAI image generator behind a small interface.
4. A one-command/manual script or CLI path to generate and attach a header image to a draft.
5. Tests with fake generator and fake WordPress client.
6. Manual execution against draft `796`.

This keeps the feature small enough to ship while avoiding a one-off image hack.
