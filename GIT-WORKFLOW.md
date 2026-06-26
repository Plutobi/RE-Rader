# GIT-WORKFLOW

> Trunk-based development with AI-specific branch, commit, and lifecycle rules.
> Enforcement: branch protection rules + CI. Human enforcement documented below each rule.

---

## Trunk Rules

| Rule | Detail |
|------|--------|
| Single trunk | `main` is the only long-lived branch |
| Merge frequency | Every active branch merges to `main` at least once per calendar day |
| Direct push to `main` | Forbidden. All changes via PR |
| Feature flags | Use flags to land incomplete work; do not hold long branches |

**Human enforcement:** `main` branch protection: require PRs, require status checks, disallow force-push.

---

## Branch Naming

### AI-generated branches

```
ai/<chat-id>-<description>
```

- `<chat-id>`: stable UUID of the originating AI conversation (same value as provenance `chat-id`)
- `<description>`: kebab-case, max 40 chars, imperative mood (`add-auth-middleware`, `fix-null-check`)
- Example: `ai/3f2a1b9c-add-auth-middleware`

### Human branches

```
feat/<description>
fix/<description>
chore/<description>
```

### Rules

- AI must not use human branch prefixes.
- Humans must not use the `ai/` prefix.
- Branch names are immutable after first push.

**Human enforcement:** CI rejects PRs from branches not matching either pattern.

---

## Commit Message Format

### AI commits

```
<type>(<scope>): <summary>

AI-generated. chat-id: <uuid>  model: <model-id>
```

- `type`: `feat | fix | refactor | test | docs | chore`
- `scope`: affected module/package (optional but preferred)
- Body line is **required** for all AI commits; CI rejects commits without it

### Human commits

Standard Conventional Commits format. Body optional.

---

## AI Branch Lifecycle

```
Day 0   : branch created from main
Day 1+  : daily merge from main required (rebase or merge commit)
Day 7   : if unmerged → auto-deleted by CI scheduled job
```

- Auto-deletion is non-recoverable from the branch; commits remain in reflog for 30 days.
- If generation is still needed after deletion: start a new chat session, new branch.
- No extensions. Staleness indicates scope creep or a blocked review; address the cause.

**Human enforcement:** GitHub Actions scheduled workflow runs nightly, deletes `ai/*` branches with last commit > 7 days old and no open PR. Branches with an open PR are exempt until PR is closed.

---

## Merge Strategy

| Scenario | Strategy |
|----------|----------|
| AI branch → main (PR approved) | Squash merge; squash commit carries AI-generated body |
| Human branch → main | Merge commit or squash; team preference |
| main → AI branch (staying current) | Rebase preferred; merge commit acceptable |

**No merge commits from AI branches on main.** Squash keeps trunk history readable.

---

## Tagging & Releases

- Tags on `main` only, semver (`v1.2.3`).
- AI-generated releases must be tagged by a human.
- Tag message must note if the release is predominantly AI-generated: `AI-assisted release`.

---

## Quick Reference

```
# Start AI work
git checkout main && git pull
git checkout -b ai/<chat-id>-<description>

# Stay current (daily)
git fetch origin main && git rebase origin/main

# Commit
git commit -m "feat(scope): summary

AI-generated. chat-id: <uuid>  model: <model-id>"

# Push
git push origin ai/<chat-id>-<description>
# → open PR → triggers DEV-PROCESS Stage 1 CI
```
