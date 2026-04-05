# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0.0] - 2026-04-05

### Added

- `Orchestrator` class connecting all agents into two callable pipelines: `draft()` (ingest → DraftAgent → ExecutionLayer → MediaAgent → StateStore) and `publish()` (StateStore → WordPressClient → StateStore)
- End-to-end test suite for `Orchestrator` (509 tests covering draft and publish pipelines, error paths, and dependency injection)
- `context-hub` shared skill for curated API and SDK documentation via `chub`
- Documentation grounding note in `AGENTS.md` — prefer `chub` for fast-moving integrations

### Changed

- `brewpress draft` command is now fully wired — runs the complete draft pipeline end-to-end (previously a stub)
- `brewpress approve-publish` now calls the WordPress REST client after state transition — posts are actually published (previously stopped at state transition with a stub message)
- WP credentials are now validated before state transition in `approve-publish`, preventing the job from getting stuck in `APPROVED_STEP_2` if credentials are missing
- Failure bundle path is now printed to stderr when a WordPress publish fails

## [1.0.0] - 2026-04-04

### Added

- locked product requirements for BrewPress
- Claude implementation handoff
- gstack delivery plan
- shared project-level skills setup for Claude, Codex, Copilot, and Augment
- public repository bootstrap files
