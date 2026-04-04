# CoffeeTwin Final PRD

## System Name

CoffeeTwin

## Goal

Automate blog creation and publishing for DevelopersCoffee using:

- Google ADK for orchestration
- Google Flash models for reasoning and content
- WordPress REST API with Application Password auth

The system must generate:

- SEO-optimized article
- code explanations
- proof screenshots
- WordPress draft or live post

## MVP Inputs

- topic plus notes
- local git diff
- GitHub PR URL

Ignore repo URL in MVP.

## Content Types

### Code Post

Treat as code post if any of the following are true:

- git diff present
- PR URL present
- runnable commands generated

### Idea Post

Topic only, with no code proof.

Mark internally as `no-proof`.

## Pipeline

```text
Input
 -> Content Agent
 -> Code Agent
 -> Execution Layer
 -> Media Agent
 -> SEO Agent
 -> Internal Linking
 -> Review System
 -> WordPress Agent
```

## Delivery Phases

### Phase 1

- setup
- content generation
- SEO generation
- WordPress draft creation
- review state machine

### Phase 2

- code intelligence
- diff and PR grounding

### Phase 3

- execution layer with host command logging

### Phase 4

- screenshot proof generation

### Phase 5

- internal linking
- failure bundle
- end-to-end stabilization

This phase order is for delivery sequencing only.
It does not change the locked product behavior.

## Agents

### 1. Content Agent

- generates structured technical blog draft
- uses past DevelopersCoffee posts for normalized tone
- no fluff
- short paragraphs
- practical developer tone

### 2. Code Agent

- analyzes diff, PR, notes
- extracts key files and runnable logic
- generates commands
- predicts expected output

### 3. Execution Layer

- runs commands on host
- logs all commands
- stores execution trace
- no hidden execution

### 4. Media Agent

MVP only:

- terminal screenshot
- output proof screenshot

Optional:

- browser UI screenshot

### 5. SEO Agent

Generate exactly:

- 1 primary keyword
- 3 secondary keywords

Enforce:

- primary keyword in title
- primary keyword in H1 or H2
- keyword naturally present in intro

No plugin dependency.

### 6. Internal Linking

Use existing DevelopersCoffee posts.

Rules:

- 2 to 5 internal links per post
- prioritize exact topic match
- then same tags/categories
- if needed, create new tags/categories

### 7. WordPress Agent

Auth:

- Application Passwords

Endpoints:

- `/wp-json/wp/v2/posts`
- `/wp-json/wp/v2/media`

Use plugin-independent fields only.

## SEO Output Contract

```json
{
  "title": "...",
  "meta_description": "...",
  "slug": "...",
  "content": "...",
  "excerpt": "...",
  "tags": [],
  "categories": []
}
```

Inject SEO into:

- title
- headings
- first 150 words

## Review Commands

Use only these commands:

```text
revise <instruction>
approve_content
approve_publish
approve_publish publish=true
reject
```

No free-form approval language.

## Approval Logic

### `approve_content`

- marks content approved

### `approve_publish`

- create or update WordPress draft

### `approve_publish publish=true`

- publish live

Never infer live publish.

## Approval Reset Rules

### `revise` before any approval

- no reset needed

### `revise` after `approve_content`

- reset content approval

### `revise` after `approve_publish`

- reset both approvals

## Update Logic

Find post by priority:

1. slug
2. post ID
3. title search

If multiple matches:

- stop
- require explicit selection

Never auto-update ambiguous matches.

## Update Behavior

Always generate diff:

```diff
OLD
NEW
```

Default mode:

- full replace

User may later choose section patching, but not required for MVP.

## Screenshot Rule

Code posts must include:

- at least 1 terminal screenshot
- at least 1 output proof screenshot

Definition of done for code post:

```text
1 terminal + 1 output proof
```

Idea posts do not require screenshots.

## Video Policy

MVP:

- no video generation

Phase 2:

- Playwright-based scripted recording

## Trend System

Use trend scoring for topic ideation and keyword guidance.

Trend windows:

- 7 days: high weight
- 30 days: medium weight
- 90 days: low weight

Hard filter trends to:

- backend
- Java / Spring
- AI agents
- developer productivity
- system design

## Content Strategy

### Quick Post

Use when trend is short-lived and spiking.

### Evergreen Tutorial

Use when demand is stable.

## Style Policy

Use past DevelopersCoffee posts as input for:

- tone consistency
- structure
- internal linking

Do not mimic exactly.

Normalize toward:

- cleaner
- more structured
- less noisy

## Existing Corpus

Source existing posts from DevelopersCoffee via crawl or WordPress API.

Use corpus for:

- style grounding
- internal linking
- topic overlap detection

## Failure Handling

If WordPress publish/update fails:

- do not blindly retry publish
- generate local publish bundle

```json
{
  "title": "...",
  "content": "...",
  "media": [...],
  "seo": {...}
}
```

User can manually post or retry intentionally.

## Quality Gate

Draft is acceptable only if:

- publish-ready with 10 minutes or less of manual edits

If not:

- run revise loop

## User Model

MVP is single-user only.

No RBAC required.

## Deployment Model

Phase 1:

- local-first

Phase 2:

- hosted with queue and workers

## Non-Goals For MVP

- video generation
- voiceover
- multi-user roles
- WordPress SEO plugin integration
- repo URL input
