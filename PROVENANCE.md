# PROVENANCE

> Scope: every file, snippet, config, or doc created or materially modified by an AI agent.
> Enforcement: CI gate rejects artifacts missing valid provenance block. Human override documented in PR.

---

## 1. Required Metadata Block

Place at the top of every AI-generated artifact. Use the comment syntax of the target language.

```
AI-PROVENANCE
  model:        <model-id>            # e.g. claude-sonnet-4-6
  chat-id:      <uuid>                # stable ID of the originating conversation
  timestamp:    <ISO-8601-UTC>        # time of generation
  context:      <≤30-word summary>    # what problem this artifact solves
  reviewed-by:  <github-username|pending>
```

**Examples by file type**

| Type | Block syntax |
|------|-------------|
| Python / JS / TS / Go / Rust | `# AI-PROVENANCE …` or `// AI-PROVENANCE …` |
| HTML / XML | `<!-- AI-PROVENANCE … -->` |
| CSS / SCSS | `/* AI-PROVENANCE … */` |
| YAML / TOML / .env | `# AI-PROVENANCE …` |
| Markdown / plain text | `<!-- AI-PROVENANCE … -->` at line 1 |
| Binary / generated assets | Sidecar file: `<filename>.provenance.yaml` |

---

## 2. Sidecar Schema (binary / no-comment formats)

```yaml
# <filename>.provenance.yaml
model: ""
chat-id: ""
timestamp: ""
context: ""
reviewed-by: pending
```

---

## 3. Rules

- **Immutable after merge.** Do not edit provenance on merged commits; create a new artifact.
- **Partial edits.** If a human materially rewrites >50% of an AI artifact, remove the block and add a normal author comment.
- **Chained generation.** If artifact B was generated using artifact A as input, record A's chat-id in context: `"extends <chat-id-of-A>"`.
- **No fabrication.** Placeholders (`<uuid>`, `pending`) are valid pre-review; false data is a merge blocker.

---

## 4. CI Enforcement

```
check-provenance:
  - for each changed file: verify block present and parseable
  - fail if: model, chat-id, or timestamp is empty string
  - warn if: reviewed-by == "pending"
  - pass binary files only if sidecar exists
```

Gate: **required status check** on all PRs targeting `main`.
Human override: PR description must contain `PROVENANCE-OVERRIDE: <reason>`.
