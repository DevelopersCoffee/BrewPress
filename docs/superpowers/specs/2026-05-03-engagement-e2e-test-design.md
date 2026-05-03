# Engagement E2E Test Design

**Date:** 2026-05-03
**Status:** Drafted for review
**Scope:** Task 12 only

## Overview

Add one end-to-end integration test that validates the engagement pipeline contract with production-style wiring and deterministic test doubles.

The goal is not to test model quality. The goal is to prove that a healthy draft can move through the orchestrator and engagement stage, produce meaningful engagement metadata, and stop at the correct publish decision boundary without unintended side effects.

## Why This Next

The remaining work items are:

- Task 11: Knowledge base layer
- Task 12: E2E integration test
- Task 13: Documentation

If the priority is ship confidence, the highest-value uncertainty is integration behavior. Unit coverage already exists for most pieces. What is still unproven is whether the full engagement flow produces the correct final `BlogJob` outcome when the system is wired together.

## Proposed Approach

Implement a single happy-path E2E test in `tests/test_e2e_engagement_pipeline.py`.

The test should:

- enter at `Orchestrator.draft()` or the closest current orchestrator seam that includes engagement-stage wiring
- use deterministic fakes for upstream content-generation agents
- use deterministic doubles for LLM-dependent engagement components when needed
- avoid real WordPress, network, or external model calls
- assert the returned `BlogJob` contract rather than internal method ordering

This is intentionally one narrow test, not a full matrix.

## Architecture

### Test Boundary

The primary boundary is the orchestrator, because that is where confidence matters most:

- upstream agents produce a valid technical post
- engagement processing runs through real wiring
- the final job returned by the orchestrator reflects engagement scoring and publish decision logic

The test should not bypass the orchestrator and call individual engagement tools directly. That would only repeat existing lower-level tests.

### Test Doubles

Use deterministic doubles for components that are otherwise unstable or external:

- `WriterAgent`, `StructurerAgent`, `SEOAgent`, `CriticAgent`
- any LLM-backed engagement checker or fixer, if those components are part of the current integrated path
- WordPress publishing or network persistence beyond the normal test store

Keep the real orchestrator logic in play. Keep real decision propagation in play. Replace only the expensive or nondeterministic collaborators.

## Data Flow

The test data flow is:

1. Create a realistic draft input with code-oriented content.
2. Inject upstream pipeline doubles that return a post eligible for engagement evaluation.
3. Run the orchestrator draft path with engagement-stage wiring enabled.
4. Receive the final `BlogJob`.
5. Assert that engagement metadata and final decision match the expected contract.

The draft body should contain enough structure and technical content to make non-zero structural and technical scores meaningful. It should not be a toy string like `"hello world"`.

## Assertions

The first E2E test should verify only externally meaningful outcomes:

- `engagement_data.structural_score` is non-default and greater than zero
- `engagement_data.technical_score` is non-default and greater than zero
- `engagement_data.decision` matches the expected publish outcome
- `engagement_data.final_score` is populated consistently with the decision
- `execution.fixer_iterations` or equivalent execution metadata reflects the expected path
- no blocked publish path is triggered when the decision is publishable

If the current orchestrator stage returns a reviewed job instead of actually publishing, assert that exact state. The test should follow the current contract, not an aspirational one.

## Error Handling Scope

This first E2E test covers the healthy path only.

It intentionally excludes:

- retry failure behavior
- fallback and downgrade behavior
- knowledge-base updates
- post-publish metrics collection
- revision-needed outcomes

Those cases should be covered by later focused tests once the baseline path is proven.

## File Plan

Create:

- `tests/test_e2e_engagement_pipeline.py`

Likely reuse:

- existing test helpers for `BlogJob`
- existing orchestrator test patterns for injected pipelines and state store usage

Do not add broad new fixture infrastructure unless the current test suite lacks a suitable seam.

## Risks

### Risk: The current engagement stage is not fully wired at the orchestrator boundary

If this is true, the first implementation step is not to fake around it. The test should expose the missing seam clearly, then the minimum wiring needed to make the contract testable should be added.

### Risk: The test becomes brittle by asserting call order

Avoid this by asserting only returned-job state and engagement metadata.

### Risk: The test becomes a disguised unit test

Avoid this by entering through the orchestrator instead of directly invoking one engagement component.

## Success Criteria

This task is complete when:

- one E2E test exercises the orchestrated engagement path
- the test runs deterministically with no external dependencies
- the test proves the final `BlogJob` contract, not internal implementation details
- the test is narrow enough that failures point to integration regressions instead of prompt variance

## Out of Scope

- Knowledge base implementation
- Post-publish metrics collection
- README or API documentation updates
- Full failure-mode coverage
- Multiple scenario matrix for engagement decisions

## Recommendation

Build Task 12 next as a single orchestrator-level happy-path E2E test. This is the fastest route to real release confidence and the best way to expose any remaining wiring gaps before adding more capability or documentation.
