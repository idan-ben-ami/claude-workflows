---
name: beads
description: This skill should be used when working with beads issue tracking — creating issues, managing dependencies, claiming work, recording memories, or when the user mentions "beads", "bd", "issue", "track this", "create an issue", or when starting/finishing a piece of work. Also use proactively when significant work begins or a bug is discovered.
version: 1.0.0
---

# Beads Workflow

> Use a single workspace-level beads tracker (run `bd where` to find it).
> Prefer one tracker per workspace over per-repo instances to avoid fragmentation.

## Core Workflow

### 1. Starting Work — Claim Before Coding

```bash
# See what's ready to work on
bd ready

# Claim an issue before starting
bd update <id> --state in-progress --assignee "$(git config user.name)"

# If no issue exists, create one first (see §3)
```

**Rule:** Never start significant work without a beads issue. This creates traceability and survives compaction.

### 2. During Work — Leave Breadcrumbs

```bash
# Add progress notes (survives compaction, visible in bd show)
bd note <id> "Implemented the extraction logic in deterministic_extractor.py"

# Record insights that apply beyond this issue
bd remember "Priority ERP uses ZIMP_SHIPCASENUM for job orders, not the description field"

# Link discovered sub-problems
bd create "Handle edge case: O/0 mismatch in part numbers" --deps "discovered-from:<parent-id>"
```

### 3. Creating Issues — Make Them Self-Contained

Every issue should be operable by a fresh session with zero prior context.

```bash
bd create "Title: clear, actionable" \
  --description "What needs to happen and why" \
  --acceptance "How to verify it's done" \
  --context "Background: what led to this" \
  --deps "<dependency-id>" \
  --estimate 120
```

**Required fields:**
- **Title**: Action-oriented (e.g., "Add past-date guard to proposal creator", not "Date bug")
- **Description**: What + why. Reference specific files/functions. Include enough context that a fresh session can understand the problem without reading the conversation.
- **Acceptance criteria**: Concrete, testable conditions for "done"

**Optional but valuable:**
- `--context`: Business context, user reports, related issues (e.g., "Reported in ALO-94")
- `--deps`: Dependencies on other beads issues
- `--estimate`: Time estimate in minutes
- `--design`: Technical approach notes

### 4. Finishing Work — Close With Context

```bash
# Close with a summary of what was done
bd close <id> --comment "Implemented in PR #42. Added guard in proposal_creator.py:L180-195"

# If the work revealed new issues, create them
bd create "Follow-up: extend past-date guard to goods receipt handler" \
  --context "Discovered while working on <parent-id>"
```

### 5. Dependencies — The Chain

Dependencies are first-class in beads. Use them to model:

```bash
# This blocks that
bd link <blocker-id> blocks <blocked-id>

# Discovery chain (found while investigating)
bd create "Sub-issue" --deps "discovered-from:<parent-id>"

# View the dependency graph
bd children <parent-id>
bd blocked
```

**Blocked issues** won't appear in `bd ready` until their blockers are resolved.

## Memories — Cross-Session Knowledge

Memories are injected into every session via `bd prime` (runs on SessionStart hook).

```bash
# Store a persistent insight
bd remember "Always use Pydantic models for API responses" --key pydantic-responses

# Recall a specific memory
bd recall pydantic-responses

# Good memory candidates:
# - Non-obvious conventions ("field X maps to Y in the ERP")
# - Hard-won debugging insights ("phantom DBs hide in three places")
# - Architectural decisions ("auth uses NAA, not device code flow")
```

**Keep memories under ~50 total** — each one costs context tokens in every session.

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `bd ready` | Show work that's unblocked and ready |
| `bd list` | List all open issues |
| `bd blocked` | Show blocked issues and what blocks them |
| `bd show <id>` | Full issue details with notes and history |
| `bd search "keyword"` | Search issues by text |
| `bd create "title"` | Create new issue |
| `bd update <id> --state <state>` | Change state (open/in-progress/blocked) |
| `bd close <id>` | Close a completed issue |
| `bd note <id> "text"` | Add a progress note |
| `bd link <a> blocks <b>` | Create dependency |
| `bd remember "insight"` | Store persistent memory |
| `bd preflight` | PR readiness checklist |
| `bd prime` | Inject context (runs automatically via hook) |

## Cross-Repo Context

Issues naturally span repos. Use description/context to reference which repos are affected:

```bash
bd create "Add generated types for import-files endpoint" \
  --description "Backend: endpoint in api/import_files.py. Frontend: regenerate types." \
  --context "Affects: backend, frontend"
```

## Anti-Patterns

- **Don't create issues for trivial fixes** (typos, obvious one-liners)
- **Don't let issues go stale** — if in-progress for >1 week, add a note or re-assess
- **Don't duplicate external tracker issues** — reference them (`--context "Linear: ALO-94"`) instead
- **Don't store ephemeral conversation context as memories** — memories are for durable insights
