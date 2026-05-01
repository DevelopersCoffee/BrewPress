# Engagement-Optimized Publishing Pipeline Design

**RFC: Autonomous Developer-Content Intelligence System**  
**Date:** 2026-05-01  
**Author:** Claude (Brainstorming + Design)  
**Status:** Ready for Implementation Planning

---

## 1. Overview

Build an autonomous content transformation system that extends BrewPress (CoffeeTwin) to ensure technical blog posts meet engagement standards before publishing to WordPress.

**Core insight:** Correct content can still be boring. This system applies deterministic engagement rules + optional LLM improvements to maximize developer value.

**Scope:** Single blog post → WordPress publication with observability  
**Example:** Git Worktree blog (reference use case; system is domain-agnostic)

---

## 2. Problem Statement

### Current State
BrewPress generates technically correct blog posts (WriterAgent → StructurerAgent → SEOAgent → CriticAgent).

### Gap
Correctness ≠ Engagement. Posts can pass CriticAgent but still:
- Lack relatable problem statement (pain hook)
- Miss "aha moments" (surprising insights)
- Have no clear call-to-action (CTA)
- Contain no hands-on exercises
- Feel dense or impractical to developers

### Solution
Add an **EngagementAgent** as the final gate before publishing, with:
- **Deterministic structural validation** (engagement arc scoring)
- **Auto-improvement loop** (fix missing elements automatically)
- **Technical validation** (code/commands are real)
- **Tiered publish decisions** (auto-approve / publish-with-improvements / revision-needed)

---

## 3. Architecture

### 3.1 Complete Pipeline

```
Input (topic + notes, git diff, GitHub PR)
  ↓
WriterAgent (narrative generation)
  ↓
StructurerAgent (organization, headings, flow)
  ↓
SEOAgent (keywords, slug, meta description)
  ↓
CriticAgent (correctness gate: clarity, completeness, accuracy)
  ├─ If fails → STOP (reject, don't attempt engagement fix)
  └─ If passes → continue
  ↓
EngagementAgent (NEW — composed agent)
  ├─ tools: structural_checker, engagement_fixer, technical_checker, publish_gate
  ├─ Loop: validate → fix → re-validate (max 2 iterations)
  ├─ Retry: 2x per component with exponential backoff
  ├─ Fallback: mark as "unknown", never convert to failure
  └─ Cost optimization: skip if conditions met
  ↓
Sanitizer (markdown validation, escape unsafe content)
  ↓
PublisherAgent (WordPress draft/live, idempotent by slug)
  ├─ Retry: 3x exponential backoff
  ├─ Deduplicate: check if post exists before creating
  └─ On success: trigger post-publish metrics job
  ↓
Post-Publish Job (async)
  ├─ Collect metrics (CTR, read time, engagement)
  └─ Update knowledge_base with performance data
```

### 3.2 Agent Composition

**EngagementAgent** is a single composed agent (not 5 separate agents):

```python
class EngagementAgent(BaseAgent):
    tools:
      - structural_checker (LLM: evaluate engagement arc)
      - engagement_fixer (LLM: improve content)
      - technical_checker (regex + whitelist: validate code)
      - publish_gate (deterministic: score → decision)
    
    process:
      1. Check structural score (via tool)
      2. If < 80: apply fixes, re-check (loop 2x max)
      3. Check technical score (via tool)
      4. Call publish gate with both scores
      5. Return updated BlogJob
```

**Why one agent?** Simpler orchestration, cleaner ADK alignment, easier observability.

---

## 4. Components

### 4.1 StructuralChecker (LLM Tool)

**Purpose:** Evaluate engagement structure using semantic understanding (not keywords).

**Input:** Blog markdown content  
**Output:** Structured score + issues list

**Scoring (100 points max):**
| Rule | Weight | Method | Pass Condition |
|------|--------|--------|---|
| Pain statement in intro | 30pts | Semantic classification: is introduction framing a developer pain/struggle? | First 2 paragraphs contain problem-type language |
| Solution arc | 20pts | Check: is solution introduced in first 20% of content? | Solution present + links to pain |
| Aha moments | 20pts | Count `💡 Aha:` markers or equivalent callouts | ≥2 instances |
| CTA clarity | 15pts | Imperative instruction: "try", "do", "use" + concrete action | ≥1 strong CTA |
| Hands-on section | 15pts | Heading/code block labeled: "challenge", "exercise", "try", "task" | ≥1 section |

**Output:**
```json
{
  "structural_score": 75,
  "pain_present": false,
  "solution_present": true,
  "aha_count": 0,
  "cta_present": false,
  "hands_on_present": true,
  "issues": [
    "Missing strong pain hook in introduction",
    "No explicit aha moments",
    "Missing CTA"
  ]
}
```

### 4.2 EngagementFixer (LLM Tool)

**Purpose:** Auto-improve content based on identified issues.

**Input:** Blog markdown + issues list  
**Output:** Improved markdown + list of fixes applied

**Rules (priority order):**
1. Pain: If missing → rewrite intro with relatable developer pain
2. Solution: If weak → strengthen solution link to pain
3. Aha: If missing → identify 2+ surprising statements, mark as `💡 Aha: <statement>`
4. CTA: If missing → append actionable CTA at end
5. Hands-on: If missing → add "Try this" section with example

**Idempotency Guards:**
- Check if CTA already exists before adding (no duplicates)
- Count `💡 Aha:` markers; don't exceed target count
- Track applied fixes in `BlogJob.execution.fixer_actions`

**Output:**
```json
{
  "improved_content": "...",
  "fixes_applied": [
    "pain_hook_injected",
    "cta_added",
    "aha_moments_marked"
  ]
}
```

### 4.3 TechnicalChecker (Deterministic Tool)

**Purpose:** Validate code/commands are real (not hallucinated).

**Input:** Blog markdown  
**Output:** Technical score + invalid items list

**Validation (100 points max):**
| Check | Method | Score |
|-------|--------|-------|
| Bash syntax | Parse ```bash blocks; validate with `bash -n` | +40 |
| Known commands | Whitelist: git, docker, kubectl, bash builtins | +30 |
| Code tags | All code blocks labeled (```bash, ```python, etc.) | +20 |
| No hallucinations | Exclude impossible tools (git magic-branch, npm deploy) | +10 |

**Output:**
```json
{
  "technical_score": 92,
  "invalid_commands": [],
  "missing_language_tags": false,
  "issues": []
}
```

### 4.4 PublishGate (Deterministic Tool)

**Purpose:** Make final publish decision based on all scores.

**Input:** structural_score, technical_score  
**Output:** Decision + reasoning

**Decision Rules:**
| Structural | Technical | Decision | Behavior |
|-----------|-----------|----------|----------|
| ≥90 | ≥90 | **approved** | Auto-publish to WordPress live |
| 80–89 | 80–89 | **publish_with_improvements** | Publish to draft, flag for review |
| <80 | any | **revision_needed** | Reject, return to WriterAgent with feedback |
| any | <80 | **revision_needed** | Reject, return to WriterAgent with feedback |
| unknown | any | **publish_with_improvements** | Downgrade to safe publish (never auto-publish on missing data) |

**Output:**
```json
{
  "decision": "publish_with_improvements",
  "final_score": 86,
  "reason": "Engagement score acceptable; technical validation passed"
}
```

---

## 5. Data Schemas

### 5.1 BlogJob (Extended)

```json
{
  "id": "uuid",
  "topic": "Git Worktree best practices",
  "content_type": "tutorial|deep_dive|comparison",
  "input_source": "topic|diff|pr_url",
  
  "draft_body_md": "# Git Worktree...",
  "draft_body_md_version": "v1.0",
  
  "versioning": {
    "prompt_version": "v1.2",
    "tool_version": {
      "structural_checker": "v2.1",
      "engagement_fixer": "v1.0",
      "technical_checker": "v1.3",
      "publish_gate": "v1.0"
    },
    "model": "gemini-2.0-flash",
    "timestamp": "2026-05-01T10:00:00Z"
  },
  
  "execution": {
    "retry_count": 0,
    "max_retries": 2,
    "failed_components": [],
    "fallback_applied": false,
    "partial_success": false,
    "start_time": "...",
    "end_time": "...",
    "duration_ms": 0,
    "fixer_iterations": 1
  },
  
  "learning": {
    "hook_style": "pain|curiosity|data",
    "cta_type": "action|engagement|sharing",
    "estimated_read_time": 8,
    "code_complexity": "beginner|intermediate|advanced"
  },
  
  "critic_data": {
    "correctness_score": 92,
    "clarity_score": 88,
    "completeness_score": 85,
    "hallucination_risk": "low|medium|high"
  },
  
  "engagement_data": {
    "structural_score": 88,
    "technical_score": 92,
    "readability_score": null,
    "final_score": 90,
    "fixer_iterations_applied": 1,
    "fixer_actions": [
      "pain_hook_injected",
      "cta_added"
    ],
    "failed_rules": [],
    "decision": "publish_with_improvements",
    "confidence": 0.92
  },
  
  "override": {
    "approved": false,
    "reason": null,
    "approved_by": null,
    "timestamp": null,
    "audit_log": []
  },
  
  "publishing": {
    "wp_post_id": null,
    "wp_slug": "git-worktree-best-practices",
    "wp_status": "draft|published",
    "idempotent_key": "git-worktree-best-practices",
    "publish_timestamp": null,
    "url": null
  },
  
  "post_publish": {
    "collected": false,
    "metrics": {
      "ctr": null,
      "avg_read_time": null,
      "bounce_rate": null,
      "likes": null,
      "shares": null,
      "comments": null
    },
    "engagement_percentile": null
  }
}
```

### 5.2 Knowledge Base Schema

```json
{
  "version": "1.0",
  "last_updated": "2026-05-01T10:00:00Z",
  
  "hooks": [
    {
      "text": "Ever stashed changes and forgot what you were doing?",
      "style": "pain",
      "usage_count": 0,
      "avg_ctr": null,
      "avg_engagement": null,
      "first_used": "2026-05-01",
      "last_used": "2026-05-01"
    }
  ],
  
  "ctas": [
    {
      "text": "Try this today: create 2 worktrees for your next Jira tickets",
      "type": "action",
      "usage_count": 0,
      "avg_click_rate": null,
      "first_used": "2026-05-01"
    }
  ],
  
  "common_failures": [
    {
      "pattern": "missing_pain_hook",
      "fix_effectiveness": null,
      "occurrence_count": 0
    }
  ],
  
  "content_type_weights": {
    "tutorial": {
      "pain": 35,
      "solution": 25,
      "aha": 15,
      "cta": 15,
      "hands_on": 10
    },
    "deep_dive": {
      "pain": 20,
      "solution": 20,
      "aha": 30,
      "cta": 10,
      "hands_on": 20
    },
    "comparison": {
      "pain": 15,
      "solution": 20,
      "aha": 20,
      "cta": 20,
      "hands_on": 25
    }
  },
  
  "cold_start_templates": {
    "pain_intro": "Ever [developer_problem]? This is why most devs [pain_consequence].",
    "solution_bridge": "[Solution] eliminates this entirely.",
    "aha_marker": "💡 Aha: [surprising_insight]",
    "cta_template": "Try this [timeframe]: [concrete_action]"
  }
}
```

---

## 6. Error Handling & Resilience

### 6.1 Component Failure Modes

| Component | Failure | Retry | Fallback | Behavior |
|-----------|---------|-------|----------|----------|
| StructuralChecker | Timeout / invalid JSON | 2x backoff | Mark score = unknown | Downgrade decision |
| EngagementFixer | Produces invalid markdown | 2x backoff | Skip fix, keep original | Proceed to technical check |
| TechnicalChecker | Tool unavailable | 1x | Mark score = unknown | Allow publish if other scores pass |
| PublisherAgent | Network/auth failure | 3x backoff | Mark as "pending_publish" | Retry next cycle |

### 6.2 "Unknown" State Handling

When any component returns `unknown`:
- **Never treat as failure** — log as partial success
- **Downgrade publish decision** to "publish_with_improvements" or hold for review
- **Never auto-publish** if critical components unknown
- **Log reason** for unknown state in audit trail

```json
{
  "structural_score": 88,
  "technical_score": "unknown",
  "decision": "publish_with_improvements",
  "reason": "technical_checker unavailable; structural passed; safe publish"
}
```

### 6.3 Cost Optimization Gates

Skip EngagementAgent entirely if:
1. CriticAgent score ≥88 AND
2. Lightweight structural pre-check passes (cached or quick validation)

Skip TechnicalChecker if:
- No code blocks present in content

Set max_tokens per agent:
- WriterAgent: 2000
- EngagementFixer: 1500
- CriticAgent: 500

Use caching for identical content chunks.

---

## 7. Logging & Observability

### 7.1 Required Logs

**EngagementAgent must emit:**
```
- agent_start: { timestamp, blog_id, initial_score }
- iteration_n: { iteration, structural_score, fixes_applied, reason_for_continue }
- component_call: { tool_name, input_size, latency_ms, status }
- iteration_end: { final_score, decision, total_latency_ms }
- agent_end: { outcome, scores, decision }
```

**PublisherAgent must emit:**
```
- publish_start: { blog_id, decision, target (draft|live) }
- publish_attempt: { attempt_n, status, wp_response }
- publish_success: { wp_post_id, url, timestamp }
- idempotent_check: { existing_post_id (if any), action (create|skip) }
```

### 7.2 Metrics Collection

Track per execution:
```json
{
  "auto_approved_percent": 0.0,
  "avg_structural_score": 0.0,
  "avg_technical_score": 0.0,
  "most_common_failures": ["missing_pain", "weak_cta"],
  "fixer_success_rate": 0.0,
  "avg_iterations_needed": 0.0,
  "avg_latency_per_component": {
    "structural_checker": 1200,
    "engagement_fixer": 3400,
    "technical_checker": 250,
    "publish_gate": 50
  },
  "cost_optimizations_triggered": 12,
  "fallback_count": 2
}
```

Segment by `content_type`:
```json
{
  "by_content_type": {
    "tutorial": { avg_structural: 86.5, ... },
    "deep_dive": { avg_structural: 82.1, ... },
    "comparison": { avg_structural: 84.3, ... }
  }
}
```

---

## 8. Security & Validation

### 8.1 Sanitizer (before PublisherAgent)

```
Validate:
- Markdown structure (no broken nesting)
- Code blocks (proper syntax highlighting)
- No embedded scripts or malicious HTML
- Link validation (no javascript: protocol)
- Character encoding (UTF-8, safe for WordPress)

Escape:
- HTML special characters in markdown
- WordPress shortcode conflicts
- Unsafe URLs
```

### 8.2 Idempotency (PublisherAgent)

```
Before creating post:
1. Check if post exists by slug (idempotent_key)
2. If exists: compare content hash
   - If same content: skip create (no duplicate)
   - If different content: update existing post
3. Store wp_post_id in BlogJob for future reference
```

---

## 9. Learning Layer

### 9.1 Feedback Loop Activation

After PublisherAgent success:

```python
trigger_post_publish_job(blog_id, wp_post_id)
  → collect_metrics(wp_post_id)
  → update_knowledge_base(blog_id, metrics)
  → tune_weights_if_needed()
```

### 9.2 Knowledge Base Updates

```
For each blog published:
1. Record actual hook effectiveness (CTR vs expected)
2. Record CTA effectiveness (click rate)
3. Update content_type_weights based on performance
4. Add failure patterns to common_failures
5. Evolve templates based on high-performing posts
```

### 9.3 Cold Start Strategy

When knowledge_base is empty:
```
- Use default_templates (predefined)
- Set all weights equally
- Enable exploration_mode (more prompt variation)
- Collect metrics aggressively
- After 10 posts: switch to learned weights
```

---

## 10. Example Walkthrough: Git Worktree Blog

**Input:** Original Git Worktree blog (documentation-style, low engagement)

### Step 1: StructuralChecker

```json
{
  "structural_score": 65,
  "pain_present": false,
  "solution_present": true,
  "aha_count": 0,
  "cta_present": false,
  "hands_on_present": true,
  "issues": [
    "Missing strong pain hook in introduction",
    "No explicit aha moments",
    "Missing CTA"
  ]
}
```

### Step 2: EngagementFixer (Iteration 1)

Applies fixes:
1. Rewrite intro: "Ever stashed changes and forgot what you were doing? Yeah—this is why context switching costs hours daily."
2. Mark aha moments:
   - "💡 Aha: You can run TWO features simultaneously without switching branches"
   - "💡 Aha: Same repo, multiple directories, zero duplication"
3. Add CTA: "Try this today: create 2 worktrees for your next Jira tickets"

### Step 3: Re-check Structural

```json
{
  "structural_score": 88,
  "pain_present": true,
  "solution_present": true,
  "aha_count": 2,
  "cta_present": true,
  "hands_on_present": true,
  "issues": []
}
```

✅ Score ≥80, exit loop.

### Step 4: TechnicalChecker

```json
{
  "technical_score": 92,
  "invalid_commands": [],
  "missing_language_tags": false,
  "issues": []
}
```

### Step 5: PublishGate

```json
{
  "decision": "publish_with_improvements",
  "final_score": 90,
  "reason": "Engagement excellent (88); Technical solid (92); Safe to publish"
}
```

### Step 6: Sanitizer ✅

- Markdown valid
- Code blocks labeled
- No unsafe content

### Step 7: PublisherAgent

- Check idempotent key: "git-worktree-best-practices" → not exists
- Create WordPress draft
- Store wp_post_id

### Step 8: Post-Publish Job (async)

- Collect metrics daily for 7 days
- Update knowledge_base with hook/CTA effectiveness
- Tune structural weights for "tutorial" content type

---

## 11. Future Extensions

**Out of scope for v1, but architecture supports:**

1. **Multi-channel publishing** (LinkedIn, Dev.to, YouTube scripts)
2. **Real-time metrics dashboard** (live CTR, engagement tracking)
3. **A/B testing** (prompt variations, weight tuning)
4. **Content variants** (short-form clips, thread versions)
5. **Feedback integration** (user comments → fixes → republish)

---

## 12. Deployment Considerations

- ✅ Stateless agents (BlogJob is sole state carrier)
- ✅ Thread-safe knowledge_base (use mutex for updates)
- ✅ Async post-publish job (non-blocking)
- ✅ Retry logic with exponential backoff
- ✅ Comprehensive logging for debugging
- ✅ Cost controls (token limits, skip gates)

---

## 13. Success Criteria

**v1 is successful when:**

- ✅ 90%+ of blogs auto-approved (≥80 structural, ≥90 technical)
- ✅ 0 hallucinated code/commands in published posts
- ✅ Avg engagement score improves post-fix (baseline vs improved)
- ✅ 100% idempotent publishing (no duplicates)
- ✅ <5% of fixes cause markdown breakage
- ✅ All logs queryable + debuggable

---

## 14. Appendix: Scoring Examples

**Tutorial content type** (Git Worktree blog):
```
pain: 30pts (strong developer pain)
solution: 20pts (clear solution intro)
aha: 20pts (2+ surprising insights)
cta: 15pts (actionable CTA)
hands_on: 15pts (try-it exercise)
= 100/100 after fixes
```

**Deep-dive content type** (architecture post):
```
pain: 20pts (less emphasis)
solution: 20pts (equal)
aha: 30pts (emphasize insights)
cta: 10pts (less pushy)
hands_on: 20pts (code examples)
= 100/100 when all present
```

---

**End of Design Document**

Next phase: Implementation planning (writing-plans skill).
