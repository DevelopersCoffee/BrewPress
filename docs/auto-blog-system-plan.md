# DevelopersCoffee Auto Blog System Plan

## Goal

Build an autonomous pipeline that turns a `git diff`, repo URL, or topic into a draft-ready DevelopersCoffee blog post with:

- article content
- code snippets and explanations
- screenshots from real execution
- SEO metadata
- WordPress draft publishing

This plan uses the nearby `Coffeetwin` project as a baseline pattern for:

- CLI-first workflows
- structured artifact extraction
- Gemini Flash-backed generation
- small modular steps that fit a future `gstack` workflow

## Reality Check

The current `/Users/udaychauhan/workspace/developerscoffee.com` workspace is empty.

The best local baseline is:

- `/Users/udaychauhan/workspace/Coffeetwin`
- `/Users/udaychauhan/workspace/adk/devrel-demos-multiagent-lab`

That means the right first move is not “extend an existing app in-place.” It is to create a new service skeleton in this repo and import the useful patterns:

- `coffeetwin/cli.py`: clean command routing
- `coffeetwin/gemini_extractor.py`: structured Flash generation
- ADK sequential/parallel agents from the ADK examples

## Product Scope

### MVP

Input:

- local git diff

Output:

- blog markdown
- blog HTML
- SEO title, slug, and meta description
- terminal and browser screenshots where possible
- WordPress draft

Skip for MVP:

- video generation
- voiceover
- social posting
- multi-language generation

### Phase 2

- repo URL and PR URL ingestion
- stronger style mirroring from old DevelopersCoffee posts
- retry queue and resumable jobs
- richer media capture

### Phase 3

- short demo video generation
- auto social distribution
- newsletter packaging
- affiliate and CTA insertion

## Architecture

### Top-Level Flow

```text
Trigger
  -> Trend Scout (optional)
  -> Input Resolver
  -> Job Planner
  -> Code Analysis Lane
  -> Content Lane
  -> Media Lane
  -> SEO Lane
  -> Review Gate
  -> Composer
  -> WordPress Publisher
  -> Artifact Store + Job Report
```

### Agent Model

Use ADK with a hybrid sequential + parallel workflow:

1. `PlannerAgent`
   - normalizes the request
   - decides whether the source is a diff, repo, topic, or snippet
   - builds a job plan and shared state

2. `CodeAnalyzerAgent`
   - parses git diff or source tree
   - extracts changed files, APIs, commands, and likely runnable flows
   - proposes snippets worth embedding in the blog

3. `ContentAgent`
   - drafts the article in DevelopersCoffee style
   - uses code-analysis output as hard grounding
   - emits structured sections, not freeform prose

4. `MediaAgent`
   - executes reproducible commands in a sandbox
   - captures terminal output and browser screenshots
   - returns media manifests with captions and local paths

5. `SEOAgent`
   - creates title, slug, meta description, tags, and internal link suggestions
   - validates heading hierarchy and readability

6. `ReviewAgent`
   - presents the draft for human review in ADK buddy
   - supports revision loops and post-update flows
   - enforces explicit two-step approval before publishing

7. `PublisherAgent`
   - uploads media to WordPress
   - renders HTML
   - creates or updates a draft post idempotently

8. `CriticAgent`
   - final verification pass
   - blocks publishing if mandatory sections or assets are missing

9. `TrendScoutAgent`
   - discovers topic ideas from Google Trends and related searches
   - suggests keywords, angles, and geo-specific interest
   - proposes blog ideas that match DevelopersCoffee topics

### Orchestration Shape

Recommended ADK execution graph:

```text
SequentialAgent(root)
  - PlannerAgent
  - TrendScoutAgent
  - ParallelAgent(prep)
    - CodeAnalyzerAgent
    - StyleRetrieverTool
  - ParallelAgent(build)
    - ContentAgent
    - MediaAgent
    - SEOAgent
  - CriticAgent
  - ReviewAgent
  - PublisherAgent
```

Why this shape:

- code analysis and style retrieval can run together
- content, SEO, and media can partially run in parallel once the plan exists
- publishing must be gated by verification

## System Components

### 1. API and CLI Surface

Expose one CLI-first command before adding a web UI:

```bash
python -m developerscoffee_blog generate \
  --source-type diff \
  --source ./fixtures/sample.diff \
  --publish draft
```

Recommended commands:

- `generate`: end-to-end run
- `suggest`: trend-driven idea generation
- `plan`: dry-run execution plan
- `analyze`: diff/repo analysis only
- `render`: markdown to HTML
- `publish`: publish a prepared artifact bundle
- `update-post`: update an existing WordPress post
- `resume`: continue a failed job

### 2. Shared Job State

Use a typed job record instead of passing loose strings between agents.

Suggested model:

```python
class BlogJob:
    job_id: str
    source_type: Literal["diff", "repo", "topic", "snippet"]
    source_ref: str
    focus: str | None
    intent: Literal["new_post", "update_post", "trend_discovery"]
    target_post_id: int | None
    publish_mode: Literal["none", "draft", "publish"]
    status: Literal["queued", "running", "failed", "completed"]
    review_state: Literal["drafted", "reviewed", "approved_step_1", "approved_step_2", "rejected"]
    steps: list[JobStep]
    analysis: CodeAnalysis | None
    article: ArticleDraft | None
    seo: SeoBundle | None
    media: MediaBundle | None
    wp_result: WordPressResult | None
```

Every step should store:

- status
- started_at
- finished_at
- retry_count
- error_summary
- artifact paths

### 3. Content Grounding

Do not let the model invent implementation details.

Ground content using:

- parsed diff summary
- extracted code snippets
- execution logs
- explicit “unknown” markers when code could not run

The content prompt should require:

- problem first
- one clear architecture section
- code excerpts only from analyzed source
- exact commands that were actually run
- no claims about output unless present in logs

### 4. Media Pipeline

For MVP, keep media deterministic:

- terminal screenshots from command runs
- browser screenshots only if a preview server exists
- no video

Artifacts:

- `artifacts/<job_id>/logs/*.txt`
- `artifacts/<job_id>/screenshots/*.png`
- `artifacts/<job_id>/rendered/post.md`
- `artifacts/<job_id>/rendered/post.html`
- `artifacts/<job_id>/report.json`

### 5. WordPress Integration

Use REST API first. Do not use custom PHP endpoints unless REST is blocked.

Required operations:

- upload media
- create draft
- update existing post by id
- update existing draft by slug or stored post id
- set categories and tags
- attach featured image

Use idempotency rules:

- slug must be deterministic from generated title
- save `external_id` or `job_id` in post meta if supported
- on retry, update the same draft instead of creating duplicates

### 5A. Review and Approval Flow

The review loop should match your exact workflow:

1. You ask ADK buddy to create or update a post.
2. ADK buddy generates a draft with content, SEO, and optional media.
3. You review the draft inside ADK and request changes if needed.
4. Approval step 1 marks the draft as content-approved.
5. Approval step 2 confirms publish or update on WordPress.

Rules:

- no publish action before both approvals exist
- updates to an existing post reset approval step 2
- material draft rewrites should reset both approvals
- the review UI should show clear diff between current draft and last published version

### 6. Storage

MVP:

- local filesystem for artifacts
- SQLite for job metadata

Later:

- Postgres for job state
- Redis for queueing and retries
- GCS or S3 for durable media

## Proposed Repository Layout

```text
developerscoffee.com/
  docs/
    auto-blog-system-plan.md
  src/developerscoffee_blog/
    __init__.py
    __main__.py
    cli.py
    config.py
    models.py
    orchestrator.py
    prompts/
      content.md
      seo.md
      critic.md
    agents/
      planner.py
      content.py
      code_analyzer.py
      media.py
      seo.py
      publisher.py
      critic.py
    tools/
      git_diff.py
      code_snippet.py
      shell_exec.py
      screenshot.py
      wordpress.py
      style_retrieval.py
    render/
      markdown.py
      wordpress_html.py
    storage/
      artifacts.py
      jobs.py
    fixtures/
      sample.diff
  tests/
    test_cli.py
    test_orchestrator.py
    test_code_analyzer.py
    test_render.py
    test_wordpress.py
```

## Data Contracts

### Code Analysis Output

```json
{
  "summary": "Adds Redis-backed rate limiting to Spring Boot APIs",
  "changed_files": [
    "src/main/java/.../RateLimitInterceptor.java"
  ],
  "snippets": [
    {
      "file": "src/main/java/.../RateLimitInterceptor.java",
      "start_line": 10,
      "end_line": 42,
      "language": "java",
      "purpose": "Redis token bucket enforcement"
    }
  ],
  "commands": [
    "./gradlew test"
  ],
  "expected_outputs": [
    "HTTP 429 after threshold"
  ],
  "risks": [
    "No fallback behavior if Redis is unavailable"
  ]
}
```

### Article Draft Output

```json
{
  "title": "Spring Boot Rate Limiting with Redis",
  "slug": "spring-boot-rate-limiting-redis",
  "meta_description": "Build Redis-backed rate limiting in Spring Boot with a clean interceptor pattern.",
  "sections": [
    {"id": "problem", "heading": "The Problem", "markdown": "..."},
    {"id": "solution", "heading": "The Solution", "markdown": "..."}
  ],
  "cta": null
}
```

### Media Manifest

```json
{
  "screenshots": [
    {
      "path": "artifacts/job-123/screenshots/terminal-tests.png",
      "caption": "Running the test suite after the rate limiter changes"
    }
  ],
  "featured_image": null
}
```

## Prompting Rules

### DevelopersCoffee Voice

The system should feel:

- direct
- technical
- practical
- low-fluff
- example-driven

Hard rules:

- short paragraphs
- no invented benchmarks
- explain tradeoffs
- name failure modes
- prefer snippets over giant code dumps

### Style Retrieval

Before content generation, load historical DevelopersCoffee posts into a small retrieval corpus and extract:

- preferred title patterns
- heading rhythm
- code snippet density
- average paragraph length
- CTA style

This should influence tone, but not override factual grounding from the diff.

### Trend Discovery and SEO

Use Google Trends as an input lane, not just a reporting tool.

Trend Scout responsibilities:

- pull trending topics by country and timeframe
- compare a broad tech topic against 2 to 4 adjacent variants
- collect related and rising searches
- score whether the trend is relevant to DevelopersCoffee content
- convert trends into article angles, titles, and keyword candidates

Recommended output:

- `trend_topic`
- `why_now`
- `target_region`
- `primary_keyword`
- `secondary_keywords`
- `proposed_titles`
- `recommended_angle`

Important product rule:

- Trends should guide topic selection and SEO prioritization, but not force low-quality posts on irrelevant hype cycles

## Reliability Rules

### Mandatory Gates

Do not publish even as draft if:

- title is missing
- content has fewer than required sections
- no code-grounding evidence exists for a diff-based post
- WordPress auth is invalid
- approval step 1 and step 2 are incomplete for publish or update actions

Allow draft publishing with warnings if:

- media generation failed
- code execution failed but static analysis succeeded

### Retry Policy

- `media`: retry 1 time
- `wordpress`: retry 3 times with backoff
- `content`: retry once only if schema validation fails

### Fallbacks

If execution fails:

- keep the blog
- switch screenshots section to “expected output”
- label the post as analysis-based, not execution-verified

## Security

- keep WordPress token in environment variables or a secrets manager
- redact secrets from logs before model submission
- never send whole private repos to the model when diff slices are enough
- keep execution sandbox network-restricted by default

## Evaluation

Track quality before scaling volume.

Metrics:

- time to draft
- draft publish success rate
- average human edits before publish
- screenshot success rate
- WordPress publish retry rate
- post-level SEO score

Human review checklist:

- Is the title useful?
- Are code snippets accurate?
- Are screenshots real and relevant?
- Does the post sound like DevelopersCoffee?
- Would you publish it with under 10 minutes of editing?

Trend quality checklist:

- Is the trend relevant to developers?
- Is there a practical build angle, not just a news angle?
- Do the keywords match how developers search?
- Is the region targeting intentional?

## gstack Rollout Plan

`gstack` is not available in the local environment right now, but we should still structure the implementation exactly as a stack.

### Stack 1: Foundation

Branch: `codex/blog-foundation`

Includes:

- repo skeleton
- config and environment loading
- typed models
- CLI entrypoint
- artifact and SQLite storage

Exit criteria:

- `generate --help` works
- job record can be created and persisted

### Stack 2: Diff Analysis

Branch: `codex/blog-diff-analysis`

Depends on: `codex/blog-foundation`

Includes:

- local git diff ingestion
- file and snippet extraction
- structured `CodeAnalysis`
- golden tests for sample diffs

Exit criteria:

- sample diff produces deterministic JSON analysis

### Stack 3: Content Agent

Branch: `codex/blog-content-agent`

Depends on: `codex/blog-diff-analysis`

Includes:

- Gemini Flash content generation
- schema-validated article output
- DevelopersCoffee prompt pack
- markdown and HTML rendering

Exit criteria:

- diff input generates valid article draft and HTML locally

### Stack 4: Media Agent

Branch: `codex/blog-media-agent`

Depends on: `codex/blog-content-agent`

Includes:

- shell execution tool
- terminal log capture
- Playwright screenshot capture
- media manifest generation

Exit criteria:

- job can attach at least one screenshot when runnable

### Stack 5: SEO + Critic

Branch: `codex/blog-seo-critic`

Depends on: `codex/blog-media-agent`

Includes:

- SEO metadata generation
- Google Trends topic and keyword ingestion
- heading and length validation
- critic gate before publishing

Exit criteria:

- final draft package passes schema and quality gates

### Stack 6: WordPress Publisher

Branch: `codex/blog-wordpress-publisher`

Depends on: `codex/blog-seo-critic`

Includes:

- media upload client
- draft create/update client
- two-step approval enforcement
- idempotent publish logic
- integration tests with mocked WordPress responses

Exit criteria:

- one command produces a WordPress draft from a diff input

### Stack 7: Queue + Resume

Branch: `codex/blog-jobs-and-retries`

Depends on: `codex/blog-wordpress-publisher`

Includes:

- step retries
- resumable failed jobs
- richer job reports

Exit criteria:

- failed WordPress or media steps can resume without rerunning everything

## First 2 Weeks

### Week 1

- create project skeleton
- implement typed job models
- add diff ingestion and snippet extraction
- add content generation with strict JSON schema
- render markdown and HTML

### Week 2

- add terminal execution and screenshot capture
- add SEO agent and critic gate
- add Google Trends-backed idea and keyword suggestion
- wire WordPress draft publishing
- add two-step approval flow for publish and update
- run 3 to 5 sample posts through manual review

## Recommended First Demo

Use one known local diff and target:

- generated markdown
- generated HTML
- one terminal screenshot
- one WordPress draft

Do not include video yet.

If this demo works reliably, then expand input types and richer media.

## Build Order Recommendation

The safest order is:

1. foundation
2. diff analysis
3. content generation
4. render pipeline
5. media capture
6. WordPress draft publishing
7. retries and resume

This keeps the hardest reliability boundary, publishing, until after the content package is already stable.
