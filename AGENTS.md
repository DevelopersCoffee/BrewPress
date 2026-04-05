# BrewPress Agent Rules

These rules apply to any coding agent working in this repository.

## Security First

- Never commit, log, print, hardcode, or snapshot sensitive credentials.
- Treat all WordPress usernames, application passwords, API keys, tokens, cookies, and session material as secrets.
- This repository is intended to be public. Assume anything committed will become public.

## Approved Secret Handling

- Use environment variables for local development.
- Use untracked local config files only when explicitly ignored by git.
- Use standard secret stores or deployment platform secret managers for hosted environments.
- Keep example config files sanitized and clearly marked as examples.

## Forbidden Patterns

- No credentials in source files, markdown docs, tests, fixtures, screenshots, or terminal logs committed to git.
- No real URLs with embedded credentials.
- No sample code that encourages insecure credential handling.
- No fallback that silently reads secrets from tracked files.

## WordPress Connection Standard

- Connect to WordPress using standard secure methods only.
- For MVP, use WordPress REST API with Application Password authentication.
- Read credentials from environment variables or secure local-only configuration.
- Do not invent custom insecure auth flows.
- Do not depend on browser-copied cookies or manually pasted secrets in code.

## Logging And Artifacts

- Redact secrets from logs and failure bundles.
- Do not store raw Authorization headers.
- Do not write application passwords into screenshots, recordings, or debug output.

## If A Secret Is Needed

- Stop and use the secure configuration path.
- If the current approach would expose a secret, do not proceed with that implementation.

## Public Repo Standard

- Prefer secure-by-default examples.
- Prefer placeholder values like `YOUR_WP_APP_PASSWORD`.
- Keep all setup docs safe to copy into a public repository.

## Documentation Grounding

- For external APIs and SDKs, prefer the shared `context-hub` skill and `chub` CLI when available.
- Use curated, current docs before relying on model memory for fast-moving integrations.
