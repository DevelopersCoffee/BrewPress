# Claude Handoff

## Objective

Build the MVP of CoffeeTwin: an ADK-based multi-agent system that creates technical blog drafts for DevelopersCoffee, captures proof screenshots for code posts, supports deterministic review commands, and publishes to WordPress draft by default.

## Follow These Documents

- `/Users/udaychauhan/workspace/developerscoffee.com/docs/final-prd.md`
- `/Users/udaychauhan/workspace/developerscoffee.com/docs/gstack-delivery-plan.md`

Do not expand scope beyond those documents.

## Core Constraints

- use Google ADK
- use Google Flash models
- WordPress via REST API using Application Passwords
- no dependency on WordPress SEO plugins
- no hidden execution
- no implicit live publish
- no ambiguous update behavior

## Relevant Build Guidance

Use these implementation principles:

- build in narrow phases
- lock interfaces early
- do not introduce extra abstraction unless needed by the PRD
- test each layer before moving to the next
- prefer deterministic modules over clever agent behavior

Use the common interface shape:

```python
class Agent:
    def run(self, input) -> output
```

For tools, keep the interfaces explicit and typed.

## Required Agents

1. Content Agent
2. Code Agent
3. Media Agent
4. SEO Agent
5. WordPress Agent
6. Orchestrator

## MVP Scope

Support only:

- topic plus notes
- local git diff
- GitHub PR URL

Do not add repo URL support in MVP.

MVP media:

- terminal screenshot
- output proof screenshot

No video generation in MVP.

## Required Review Commands

Implement exactly:

```text
revise <instruction>
approve_content
approve_publish
approve_publish publish=true
reject
```

Do not support free-form approvals.

## Publish Rules

- `approve_publish` means create or update WordPress draft
- `approve_publish publish=true` means publish live
- never infer live publish implicitly

## Update Rules

Match target post by:

1. slug
2. post ID
3. title search

If title search returns multiple matches:

- stop
- require explicit user selection

Always generate OLD vs NEW diff before update.

Default update mode is full replace.

## Code Post Rules

Treat input as code post if:

- git diff exists
- PR URL exists
- runnable commands are generated

Code post must include:

- 1 terminal screenshot
- 1 output proof screenshot

If that cannot be produced, do not mark the post as fully complete.

## SEO Rules

Generate exactly:

- 1 primary keyword
- 3 secondary keywords

Ensure:

- primary keyword in title
- primary keyword in H1 or H2
- primary keyword appears naturally in first 150 words

Use plugin-independent WordPress fields only.

## Internal Linking Rules

- use existing DevelopersCoffee posts
- add 2 to 5 internal links
- prioritize topic match, then tag/category match

## Style Rules

Ground on past DevelopersCoffee posts.

Normalize style toward:

- cleaner
- structured
- concise

Do not imitate exact voice.

## Failure Rule

If WordPress publish/update fails:

- do not blindly retry final publish
- generate local publish bundle with content, media references, and SEO data

## Git And gstack Workflow

Implement using stacked branches aligned to:

1. setup
2. content base
3. code analysis
4. execution layer
5. screenshot capture
6. SEO agent
7. internal linking retriever
8. WordPress client
9. review state machine
10. orchestrator
11. failure bundle generator
12. end-to-end test

If you use `gstack`, keep the stack aligned to the product plan.

When using Claude with `gstack`, follow this lane discipline:

1. `ceo` or strategy lane
   - confirm scope, goals, and non-goals
   - do not write code here
2. `eng-manager` or planning lane
   - decide architecture, interfaces, and stack boundaries
   - do not drift into full implementation
3. `engineer` lane
   - implement only the current stack slice
   - keep changes scoped to the agreed interface
4. `qa` lane
   - validate behavior, fix defects, and verify constraints
5. `ship` or review lane
   - final pass, summary, and review readiness

Do not mix roles in one long uncontrolled session.
Keep the lane narrow and explicit.

## Commit Rules

Make local commits at the end of each logical implementation unit.

A logical unit is a self-contained reviewable slice such as:

- project bootstrap
- job state models
- trend scout
- work ingestion
- draft generation
- review state machine
- WordPress client
- orchestrator wiring
- failure bundle generation

Rules:

- do not batch unrelated work into one commit
- do not wait until the end of the full project to commit
- keep commits local unless explicitly asked to push
- use short specific commit messages

Examples:

- `feat: scaffold coffeetwin adk project`
- `feat: add review approval state machine`
- `feat: add wordpress draft publishing client`

After each logical commit, report:

- what was implemented
- what remains in the current stack
- risks or follow-ups

## Suggested Phase Order

Use this implementation order:

### Phase 1

- project setup
- content agent
- SEO agent
- WordPress draft client
- review state machine
- basic orchestrator

Goal:

- generate, review, publish draft

### Phase 2

- code agent
- diff and PR ingestion
- structured code grounding

Goal:

- make posts evidence-backed

### Phase 3

- execution layer
- host command runner
- execution log storage

Goal:

- visible proof generation

### Phase 4

- terminal screenshot capture
- output proof capture
- media agent integration

Goal:

- satisfy MVP proof requirements for code posts

### Phase 5

- internal linking
- final orchestrator wiring
- failure bundle generation
- end-to-end validation

Goal:

- complete deterministic MVP

## Delivery Style

- prefer typed contracts
- prefer modular tools over monolithic agent logic
- keep each branch and commit reviewable
- optimize for deterministic behavior over cleverness
- do not add speculative features

## Final Output Expected From Claude

Claude should implement:

- project structure
- agent modules
- tool interfaces
- review state machine
- WordPress publishing client
- screenshot proof flow
- orchestration wiring
- failure bundle generation

Claude should also leave the repo in a state where:

- logical local commits exist
- the stack is reviewable
- MVP behavior matches the PRD exactly
