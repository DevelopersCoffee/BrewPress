# DevelopersCoffee gstack Delivery Plan

## Role Framing

This document is written from the product owner perspective.

Goal:

- define the stacked delivery plan
- define what Claude should implement in each stack
- keep architecture, acceptance criteria, and rollout disciplined

This is not an implementation document.
It is the delivery contract for the engineering agent.

## Product Intent

We are building an ADK-based blog assistant for DevelopersCoffee.

The assistant should:

- create a new blog post from a topic plus work summary
- use your real work as grounding
- improve quality with trend and SEO signals
- support review inside ADK
- require 2-step approval before publishing
- support updating an existing blog post

## gstack Goal

Use stacked branches so Claude can implement incrementally with low risk.

Each stack should:

- be independently reviewable
- have narrow scope
- include tests where practical
- move the product one usable step forward

## Working Assumption

`gstack` is not currently installed in the local environment, so this plan defines the intended stack structure and command flow.

Once the repo is initialized and `gstack` is available, engineering should use a branch stack aligned to the order below.

## Stack Summary

### Stack 0: Repo Bootstrap

Branch:

- `codex/blog-bootstrap`

Purpose:

- create the initial project skeleton for the ADK blog assistant

Scope:

- Python project structure
- ADK-ready app layout
- CLI entrypoint
- config loading
- environment variable strategy
- placeholder tests
- docs index

Out of scope:

- real generation
- WordPress publishing
- trend ingestion

Acceptance criteria:

- repository has a clean runnable skeleton
- local command help works
- docs explain setup expectations

Claude handoff:

```text
Create the initial project skeleton for the DevelopersCoffee ADK blog assistant.
Do not implement business logic yet.
Set up the package structure, CLI entrypoint, config module, models module, docs placeholders, and test scaffolding.
Optimize for clean future extension by separate agents and tools.
```

### Stack 1: Job Model and Review State

Branch:

- `codex/blog-job-state`

Depends on:

- `codex/blog-bootstrap`

Purpose:

- define the core workflow state before adding generation

Scope:

- `BlogJob` model
- step tracking
- review state tracking
- approval step 1 and approval step 2 model
- new post vs update post intent
- simple local persistence strategy

Acceptance criteria:

- job state can represent draft, review, approval, reject, publish-ready states
- update flows are represented explicitly
- approval state is impossible to bypass in the model

Claude handoff:

```text
Implement typed workflow and persistence models for the blog assistant.
The system must support new posts, post updates, and a strict two-step approval process before publish.
Focus on state design, not UI polish.
```

### Stack 2: Topic and Trend Discovery

Branch:

- `codex/blog-trend-scout`

Depends on:

- `codex/blog-job-state`

Purpose:

- help the user discover what to write based on global and regional demand

Scope:

- Trend Scout module
- topic suggestion workflow
- keyword suggestion workflow
- rising query capture
- region-aware suggestions
- idea scoring for DevelopersCoffee fit

Product requirements:

- trends should inspire content, not force irrelevant posts
- keywords must stay developer-relevant
- output must include why-now reasoning

Acceptance criteria:

- user can ask for topic ideas
- system returns topic suggestions, angles, and keywords
- output distinguishes hype from practical developer value

Claude handoff:

```text
Implement a Trend Scout capability for the blog assistant.
Its job is to suggest blog ideas, angles, and SEO keywords using trend signals.
The output must be structured and tuned for technical blog relevance, not generic news chasing.
Do not implement publishing in this stack.
```

### Stack 3: Work Ingestion and Code Analysis

Branch:

- `codex/blog-work-ingestion`

Depends on:

- `codex/blog-trend-scout`

Purpose:

- transform the user's actual work into grounded blog inputs

Scope:

- local diff ingestion
- repo input normalization
- notes/work-summary ingestion
- code snippet extraction
- command extraction
- risk and tradeoff extraction

Acceptance criteria:

- user can provide work notes and a diff
- system produces a structured technical summary
- output is suitable as hard grounding for content generation

Claude handoff:

```text
Implement the work-ingestion and code-analysis layer.
The user may provide a topic, notes, diff, repo details, or combinations of these.
Produce structured technical grounding that a content agent can safely use without inventing details.
```

### Stack 4: Draft Generation Agent

Branch:

- `codex/blog-draft-agent`

Depends on:

- `codex/blog-work-ingestion`

Purpose:

- create meaningful first drafts in DevelopersCoffee style

Scope:

- ADK content agent
- prompt templates
- article schema
- title, slug, and meta generation
- sectioned markdown output
- support for trend-informed, work-grounded drafts

Product rules:

- no fluff
- practical dev tone
- short paragraphs
- real examples only
- do not invent missing facts

Acceptance criteria:

- user can request a new draft
- system generates a structured post with SEO metadata
- draft is grounded in the provided work context

Claude handoff:

```text
Implement the draft generation agent for DevelopersCoffee.
It must produce meaningful, structured technical blog drafts using the user's work as grounding and optional trend/keyword guidance.
Tone should be direct, developer-first, and low-fluff.
```

### Stack 5: Review Loop and Approval Guard

Branch:

- `codex/blog-review-gate`

Depends on:

- `codex/blog-draft-agent`

Purpose:

- make the review loop safe and explicit before any publishing exists

Scope:

- review commands and states
- revise-draft flow
- approval step 1
- approval step 2
- reset behavior after material edits
- publish blocked unless both approvals are present

Acceptance criteria:

- draft can be revised multiple times
- approvals are visible and auditable
- any material change invalidates the right approval state

Claude handoff:

```text
Implement the review and approval guardrails for the blog assistant.
The user must be able to review, revise, approve content, and then separately approve publish/update.
Publishing must remain impossible unless both approvals are satisfied.
```

### Stack 6: WordPress Draft and Update Operations

Branch:

- `codex/blog-wordpress-ops`

Depends on:

- `codex/blog-review-gate`

Purpose:

- connect the reviewed draft to WordPress

Scope:

- create draft post
- update existing post
- slug handling
- category and tag mapping
- idempotent update behavior
- publish after approval only

Acceptance criteria:

- reviewed draft can be sent to WordPress as a draft
- existing post can be updated safely
- duplicate posts are avoided on retries

Claude handoff:

```text
Implement the WordPress operations layer for the blog assistant.
Support creating drafts and updating existing posts with idempotent behavior.
Respect the two-step approval flow already defined in the system.
```

### Stack 7: Media and Enrichment

Branch:

- `codex/blog-media-enrichment`

Depends on:

- `codex/blog-wordpress-ops`

Purpose:

- make posts richer without blocking the core workflow

Scope:

- terminal capture
- screenshot manifests
- optional hero/featured media support
- media upload hooks

Acceptance criteria:

- media is additive, not a publish blocker
- draft can include screenshots when available
- failures degrade gracefully

Claude handoff:

```text
Implement media enrichment for the blog assistant.
Add support for terminal output capture and screenshot packaging in a way that improves drafts but does not block the primary content workflow.
```

### Stack 8: Reliability and Resume

Branch:

- `codex/blog-reliability`

Depends on:

- `codex/blog-media-enrichment`

Purpose:

- make the workflow operationally usable

Scope:

- retries
- resumable jobs
- artifact reports
- failure classification
- step-level recovery

Acceptance criteria:

- failed jobs can resume from the correct step
- publish/update retries do not duplicate output
- artifact report is human-readable

Claude handoff:

```text
Implement operational reliability for the blog assistant.
Add retries, resume support, error classification, and job reporting so the system is practical for repeated content operations.
```

## User Stories

### New Post

As a developer blogger,
I want to tell ADK buddy what I built,
so it can draft a meaningful technical post for review and later publish it after my two-step approval.

### Update Existing Post

As a site owner,
I want to refresh an existing blog post with new work or improvements,
so I can keep older content current without rewriting from scratch.

### Trend-Based Ideation

As a content owner,
I want ADK buddy to suggest relevant developer blog topics based on trend signals,
so I can write timely posts with stronger keyword and SEO alignment.

## Commands Product Wants

Engineering should eventually support these user-facing intents:

- `suggest`
- `draft`
- `review`
- `approve-content`
- `approve-publish`
- `publish`
- `update-post`
- `resume`

## Review Rules

The product rules are strict:

- no direct publish from first draft
- no publish after only one approval
- content changes after approval must reset the relevant approval state
- updating an existing post must also pass the 2-step approval flow

## Trend Policy

Trend data should influence:

- topic discovery
- title direction
- keyword selection
- meta description strategy
- region targeting

Trend data should not override:

- technical truth
- user intent
- DevelopersCoffee editorial quality

## Definition of Done

The system is acceptable when:

- user can ask for topic suggestions
- user can create a draft from topic plus work-done notes
- user can review and revise in ADK
- user can give two explicit approvals
- system can create or update the WordPress post only after those approvals

## Recommended Implementation Order for Claude

Use this exact sequence:

1. Stack 0: bootstrap
2. Stack 1: job state
3. Stack 2: trend scout
4. Stack 3: work ingestion
5. Stack 4: draft generation
6. Stack 5: review gate
7. Stack 6: WordPress ops
8. Stack 7: media enrichment
9. Stack 8: reliability

## Notes for Engineering Agent

- optimize for small reviewable diffs
- prefer typed contracts over implicit strings
- block unsafe publish behavior at the model and service layer
- treat media as optional in MVP
- trend discovery is important, but publishing safety is more important
