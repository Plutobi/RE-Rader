# DEV-PROCESS

> Three-stage pipeline for all AI-assisted work. Each stage is a hard gate; work cannot skip forward.
> Enforcement: CI/CD blocks merge until all gates pass. Human gates require explicit approval.

---

## Stages at a Glance

```
[Stage 1: AI Generation] → CI gate → [Stage 2: AI Review] → AI-review gate → [Stage 3: Human Review] → human approval → merge to main
```

---

## Stage 1 — AI Generation

**Owner:** AI agent  
**Branch:** `ai/<chat-id>-<description>` (see GIT-WORKFLOW.md)

### Requirements before advancing

| Check | Method | Blocks on failure |
|-------|--------|-------------------|
| Provenance block present and valid | CI: `check-provenance` | yes |
| All existing tests pass | CI: test suite | yes |
| New code has tests (if testable) | CI: coverage delta ≥ 0 | warn only (first 30 days), then block |
| No secrets / credentials in diff | CI: secret-scan | yes |
| Artifact committed with chat-id reference | commit message lint | yes |

**Commit message format**
```
<type>(<scope>): <summary>

AI-generated. chat-id: <uuid>  model: <model-id>
```

---

## Stage 2 — AI Review

**Owner:** AI agent (different model or session from Stage 1)  
**Trigger:** automatic on PR open / push, after Stage 1 gates pass

### Review dimensions

| Dimension | What to check |
|-----------|--------------|
| Security | Injection vectors, auth bypass, secret exposure, unsafe deserialization |
| Performance | N+1 queries, unbounded loops, blocking I/O in hot paths, memory leaks |
| Style | Naming conventions, file structure, dead code, comment accuracy |
| Provenance integrity | Block present, chat-id matches branch name, no fabricated values |

### Output

AI reviewer posts a structured report as a PR comment:

```
AI-REVIEW
  passed: [security, performance, style, provenance]  # or subset
  failed: []
  warnings: []
  notes: <≤50 words>
```

**Gate:** PR is blocked until `AI-REVIEW passed` list covers all four dimensions.  
Human override: PR description must contain `AI-REVIEW-OVERRIDE: <dimension> <reason>`.

---

## Stage 3 — Human Review

**Owner:** human engineer  
**Trigger:** after Stage 2 gate passes

### Scope — what humans review

| Concern | Questions to answer |
|---------|---------------------|
| Architecture fit | Does this belong here? Does it introduce unwanted coupling? |
| Intent alignment | Does the output match what was asked, including implicit constraints? |
| Long-term maintenance | Will a human be able to modify this without AI assistance? |
| Risk acceptance | Are the AI-review warnings acceptable for this context? |

### What humans do NOT re-check

Humans trust Stage 2 for security/performance/style details unless Stage 2 was overridden.

### Gate

- Minimum **1 human approval** on PR (repo branch protection rule).
- If AI-REVIEW-OVERRIDE was used: minimum **2 human approvals**.
- Reviewer must not be the person who initiated the AI generation session.

---

## Escalation

| Situation | Action |
|-----------|--------|
| Stage 1 CI failing repeatedly on same issue | Open a human task; do not loop AI indefinitely |
| Stage 2 flags security issue | Block PR; human must explicitly accept risk in writing |
| Stage 3 reviewer disagrees with AI architecture | Reject PR; re-scope in a new chat session |
| Unmerged AI branch > 7 days | Auto-deleted (see GIT-WORKFLOW.md); re-generate if still needed |
