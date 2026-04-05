# BrewPress

BrewPress is an ADK-powered technical publishing engine for DevelopersCoffee.

It turns topics, notes, git diffs, and PRs into structured technical blog posts with:

- code-aware draft generation
- proof-oriented screenshots for code posts
- SEO metadata and internal linking
- deterministic review commands
- safe WordPress draft-first publishing

## Why BrewPress

Writing technical blogs is usually a fragmented workflow:

1. summarize the work
2. extract the useful code
3. explain the implementation
4. create screenshots
5. optimize for SEO
6. upload to WordPress

BrewPress automates that pipeline while keeping editorial control with a strict review and approval flow.

## MVP Scope

Inputs:

- topic plus notes
- local git diff
- GitHub PR URL

Outputs:

- structured technical draft
- SEO title, excerpt, slug, and keywords
- proof screenshots for code posts
- WordPress draft by default

## Core Workflow

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

## Review Commands

```text
revise <instruction>
approve_content
approve_publish
approve_publish publish=true
reject
```

Publishing rules:

- `approve_publish` creates or updates a WordPress draft
- `approve_publish publish=true` publishes live

## Project Status

This repository currently contains the locked product spec, delivery plan, and Claude implementation handoff for `v1.0.0`.

Implementation is intentionally guided by:

- a deterministic PRD
- a stacked delivery plan
- project-level shared skills for Claude, Codex, Copilot, and Augment

## Repo Structure

```text
docs/
  final-prd.md
  claude-handoff.md
  gstack-delivery-plan.md
  auto-blog-system-plan.md
.agents/skills/
  context-hub/
  find-skills/
  wp-rest-api/
```

## Skills

This repo uses a single shared skills source at `.agents/skills`, symlinked into:

- `.claude/skills`
- `.augment/skills`
- `.codex/skills`
- `.github/skills`

Shared skills currently include:

- `context-hub` for curated, up-to-date API and SDK docs via `chub`
- `find-skills` for discovering installable agent skills
- `wp-rest-api` for WordPress REST API implementation and debugging

## Getting Started

### 1. Clone and install

```bash
git clone git@github.com:DevelopersCoffee/BrewPress.git
cd BrewPress
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in real values:

| Variable | Description |
|---|---|
| `WP_URL` | Your WordPress site URL (`https://` required) |
| `WP_USERNAME` | WordPress username for the Application Password |
| `WP_APP_PASSWORD` | Generated via **WP Admin → Users → Profile → Application Passwords** |
| `GOOGLE_API_KEY` | Google AI API key for draft generation |

> **Never commit `.env`.** It is git-ignored by default.

### 3. Sanity check

Verify the WordPress connection and list your 5 most recent posts:

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
brewpress --version
```

A successful connection will authenticate via WordPress Application Password over HTTPS.

### 4. Generate your first draft

```bash
brewpress draft --topic "your topic here"
```

### 5. Review and publish

```bash
brewpress review
brewpress approve-content
brewpress approve-publish          # saves as WordPress draft
brewpress approve-publish --live   # publishes live
```

### GitHub Actions / CI

Secrets are stored in the repository under **Settings → Secrets → Actions**:

- `WP_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD`

Reference them in workflows as `${{ secrets.WP_URL }}` etc.

### Implementation docs

1. `docs/final-prd.md`
2. `docs/gstack-delivery-plan.md`
3. `docs/claude-handoff.md`

## Roadmap

- `v1.0.0`: local-first MVP with draft-safe WordPress publishing
- `v1.1.0`: richer code grounding and internal linking
- `v1.2.0`: proof media upgrades and more resilient execution
- `v2.0.0`: hosted queueing, async workers, and multi-run orchestration

## License

[Apache-2.0](./LICENSE)
