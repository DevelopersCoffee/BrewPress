---
name: context-hub
description: Use when a task needs current, curated API or SDK documentation for a library, framework, or platform and the Context Hub CLI (`chub`) is available. Search for docs with `chub search`, fetch them with `chub get`, and prefer them over guessing or stale memory.
---

# Context Hub

## When to use

Use this skill when the user needs:

- current API or SDK docs
- exact method names, parameters, or request shapes
- language-specific examples from maintained documentation
- less hallucination risk than recalling docs from memory

This is especially useful for fast-moving providers like OpenAI, Stripe, Vercel, Supabase, and similar platforms.

## Workflow

1. Confirm the package, provider, or topic to look up.
2. Run `chub search <query>` to find the best matching doc.
3. Run `chub get <id>` and add `--lang py` or `--lang js` when the language matters.
4. Read only the fetched content you need, then implement against that doc.
5. If the doc is missing an important caveat, add a local note with `chub annotate <id> "<note>"`.

## Command patterns

```bash
chub search openai responses
chub get openai/chat --lang py
chub get stripe/api --lang js
chub annotate stripe/api "Webhook verification requires the raw request body"
```

## Guidance

- Prefer `chub` over ad-hoc web search when both are available.
- Prefer the language variant that matches the codebase you are editing.
- Keep fetched scope small unless the task clearly needs `--full`.
- If `chub` is not installed or does not have the needed content, fall back to primary official docs and say so briefly.
