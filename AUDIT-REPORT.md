# AUDIT REPORT — Cross-File Review
> Reviewer: Claude Opus (independent model, no authorship context)
> Files reviewed: PROVENANCE.md, DEV-PROCESS.md, GIT-WORKFLOW.md, PROJECT-OVERVIEW.md

---

## 1. Conflicts / Contradictions

**1.1 — Branch-name-to-chat-id binding contradicts the >50% rewrite rule**
GIT-WORKFLOW.md states `<chat-id>` in the branch is the "same value as provenance `chat-id`", and DEV-PROCESS.md Stage 2 requires "chat-id matches branch name." But PROVENANCE.md §3 says: if a human rewrites >50%, "remove the block and add a normal author comment." Once the provenance block is removed, there is no chat-id to match the branch name — yet the branch (and PR) still flows through Stage 2, whose provenance-integrity check ("Block present, chat-id matches branch name") will fail. No file resolves how a >50%-rewritten artifact on an `ai/` branch passes Stage 2.

**1.2 — Squash merge destroys the per-file commit body that CI requires**
GIT-WORKFLOW.md mandates an AI commit body ("Body line is required for all AI commits; CI rejects commits without it") AND uses **squash merge** for AI branches ("squash commit carries AI-generated body"). A squash collapses many commits into one body; if a branch has multiple AI commits with differing chat-ids/models, the squash can only carry one. Nothing specifies which chat-id/model survives, conflicting with the assumption (1.1) that one branch = one chat-id.

**1.3 — "Reviewer must not be the person who initiated" vs. single-approval minimum**
DEV-PROCESS.md Stage 3 requires "Minimum 1 human approval" and "Reviewer must not be the person who initiated the AI generation session." For AI-initiated work the initiator is an AI agent, not a person, so the exclusion is vacuous — but if a human initiated the session via the AI, the rule can deadlock a solo/small team (the only available approver is excluded). No fallback is stated.

**1.4 — Daily-merge requirement vs. squash-only trunk history**
GIT-WORKFLOW.md Trunk Rules: "Every active branch merges to `main` at least once per calendar day." But the AI Branch Lifecycle and Merge Strategy describe AI branches landing on `main` only once, via a single approved squash-merge PR after all three stages. An in-progress AI branch cannot "merge to main" daily without passing all gates each day. The "merge frequency" rule and the staged gating model contradict each other for AI branches. (The Quick Reference resolves "stay current" as `rebase origin/main` — i.e. pulling *from* main, the opposite direction of the stated rule — suggesting the trunk rule's wording is itself wrong/ambiguous.)

**1.5 — Override approval counts cover AI-REVIEW-OVERRIDE but not PROVENANCE-OVERRIDE**
DEV-PROCESS.md: "If AI-REVIEW-OVERRIDE was used: minimum 2 human approvals." PROVENANCE.md defines a separate `PROVENANCE-OVERRIDE: <reason>` mechanism but sets no extra approval requirement. A provenance override (missing origin metadata) needs only 1 approval, while an AI-review override needs 2.

---

## 2. Redundancies (single-source-of-truth violations)

**2.1 — Commit message format defined twice, verbatim**
The commit body block appears in both DEV-PROCESS.md (Stage 1) and GIT-WORKFLOW.md. GIT-WORKFLOW.md additionally enumerates allowed `type` values and the "body required" rule; DEV-PROCESS.md does not. If one changes, the other silently diverges.

**2.2 — Branch naming pattern duplicated in three files**
`ai/<chat-id>-<description>` with its constraints lives in GIT-WORKFLOW.md (canonical), restated in DEV-PROCESS.md Stage 1 and PROJECT-OVERVIEW.md Contribution Paths — without the 40-char/kebab/imperative constraints.

**2.3 — 7-day auto-deletion stated in three files**
GIT-WORKFLOW.md (Day 7 lifecycle), DEV-PROCESS.md Escalation, and PROJECT-OVERVIEW.md Key Constraints. Three copies of one number.

**2.4 — Provenance-block requirement restated across all four files**
PROVENANCE.md §1 (canonical), DEV-PROCESS.md Stage 1 gate, PROJECT-OVERVIEW.md Contribution Paths step 3.

**2.5 — PR merge requirements in PROJECT-OVERVIEW.md already diverge**
PROJECT-OVERVIEW.md Key Constraints restates DEV-PROCESS.md gates but omits the conditional 2-approval rule for AI-REVIEW-OVERRIDE.

---

## 3. Terminology Gaps

**3.1 — "materially modified" undefined except by one threshold**
PROVENANCE.md scope says "created or materially modified," and §3 says "materially rewrites >50%." Whether both mean the same 50% threshold is never stated. CI gates trigger on *any* changed file, not "material" change — so the term has no enforced definition.

**3.2 — "Kaltmiete," "Warmmiete," "Spekulationsfrist" appear only in PROJECT-OVERVIEW.md, undefined**
Domain rules referencing German real-estate terms appear in Key Constraints with no definition, no home doc, and no enforcement mechanism. "What This Project Does" is still a placeholder.

**3.3 — "chat-id" / "session" / "conversation" used interchangeably**
PROVENANCE.md uses `chat-id` ("stable ID of the originating conversation"). DEV-PROCESS.md uses "session." GIT-WORKFLOW.md uses "originating AI conversation" and "new chat session." Three terms for one concept; no equivalence statement.

**3.4 — "merges to main" used for two opposite directions**
GIT-WORKFLOW.md Trunk Rules say branches "merge to `main` … once per calendar day," but the Quick Reference and Lifecycle describe `rebase origin/main` (pulling *from* main). "Merge" conflated for both directions.

**3.5 — "testable" undefined**
DEV-PROCESS.md Stage 1: "New code has tests (if testable)." No criterion defines what counts as testable.

**3.6 — "predominantly AI-generated" for releases undefined**
GIT-WORKFLOW.md Tagging: "predominantly AI-generated." No threshold given (contrast the precise >50% in PROVENANCE.md).

**3.7 — `reviewed-by` field never linked to Stage 3 approval**
PROVENANCE.md has `reviewed-by: <github-username|pending>`. DEV-PROCESS.md records approval via PR approvals. Whether `reviewed-by` must be populated from the Stage 3 approver, and when "pending" must become a name, is never stated. CI only warns on `pending`, so a fully merged artifact can permanently read `reviewed-by: pending`.

---

## 4. Missing Rules (implied but not stated)

**4.1 — No mechanism to update `reviewed-by` before the immutability lock**
PROVENANCE.md §3 says provenance is immutable after merge. But `reviewed-by` starts as `pending` and must become a username at Stage 3 — which happens at merge time. The two rules collide; no file sequences them.

**4.2 — Sidecar `.provenance.yaml` files have no lifecycle rules**
PROVENANCE.md defines sidecars but does not say whether editing a sidecar later counts as a provenance edit, whether the sidecar itself needs a block, or what happens if the binary changes but the sidecar does not.

**4.3 — No remediation loop for Stage 2 failures**
DEV-PROCESS.md Stage 2 has a `failed: []` field and blocks the PR, but states no remediation path: who fixes it, on what branch, and whether the fix re-enters Stage 1. Escalation only covers security-flagged PRs.

**4.4 — Override mechanisms have no authorization or audit rules**
Three override strings exist (`PROVENANCE-OVERRIDE`, `AI-REVIEW-OVERRIDE`, plus an implicit human override). No file says who may write an override, whether it is logged/reviewed, or whether overrides expire.

**4.5 — "One branch = one chat-id" never stated explicitly**
Branch name embeds one chat-id; provenance blocks may differ per file on the same branch. Whether a single `ai/` branch may contain work from multiple chat sessions is unaddressed, yet the commit-body and Stage-2 provenance check implicitly assume one-to-one.

**4.6 — No precedence clause among the four docs**
PROJECT-OVERVIEW.md is the "Living entry point" but restates rules from other files. No document declares which file wins when copies disagree.

**4.7 — `context` field overloaded between summary and lineage**
PROVENANCE.md §1 defines `context` as "≤30-word summary"; §3 Chained Generation overwrites the same field with `"extends <chat-id-of-A>"`. No rule for combining both, and §4 CI does not validate `context` format or chain references.

**4.8 — AI modification of a human-authored file has no defined provenance state**
Scope covers AI "materially modifying" human files. PROJECT-OVERVIEW.md says "provenance not required for human-authored files." What happens when an AI materially edits a previously human-authored file is left undefined — the mirror image of the >50%-rewrite rule.

---

## Files Most Entangled

- **DEV-PROCESS.md ↔ GIT-WORKFLOW.md**: duplicated commit/branch specs (2.1, 2.2), squash-vs-body and chat-id-binding conflicts (1.1, 1.2), daily-merge contradiction (1.4, 3.4).
- **PROVENANCE.md ↔ DEV-PROCESS.md**: immutability vs. `reviewed-by` population (4.1, 3.7), override approval gap (1.5), Stage-2 provenance-integrity vs. >50% block removal (1.1).
- **PROJECT-OVERVIEW.md**: acts as an unmaintained mirror (2.3, 2.5, 4.4) and sole, unsupported home of undefined domain constraints (3.2).
