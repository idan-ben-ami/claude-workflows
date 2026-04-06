---
name: plan-and-track
description: This skill should be used when starting significant new work that needs a comprehensive plan — features, investigations, refactors, or multi-step tasks. Use when the user says "plan this", "write a plan", "let's plan", "design this", "figure out how to", or when you recognize that upcoming work is non-trivial and would benefit from a written plan before coding. Also use proactively when a task spans multiple files, repos, or sessions.
version: 1.0.0
---

# Plan and Track

> Create a comprehensive, compaction-safe plan and corresponding beads issue so that any fresh session can pick up the work without prior context.

## When to Use

- New feature development
- Multi-step refactors
- Investigations that will span multiple sessions
- Any work that touches 3+ files or 2+ repos
- Work that the user explicitly wants documented

## Workflow

### Phase 1: Research

Before writing anything, understand the landscape:

1. **Read relevant code** — don't plan against assumptions
2. **Check existing plans** — `ls alora-docs/plans/` for prior work in the area
3. **Check beads** — `bd search "keyword"` for related issues, `bd blocked` for dependency context
4. **Check Linear** — if there's a related ALO- ticket, reference it
5. **Read CLAUDE.md** — ensure the plan follows established patterns

### Phase 2: Write the Plan

Create a markdown file at `alora-docs/plans/YYYY-MM-DD-descriptive-name.md`.

**The plan MUST be self-contained.** A developer (or Claude session) reading this plan with zero prior context should be able to:
- Understand what needs to happen and why
- Know exactly which files to read/modify
- Follow the implementation sequence
- Verify the work is complete

#### Plan Template

```markdown
# [Feature/Task Name]

## Context & Motivation

Why this work exists. Business context, user need, or technical driver.
Reference Linear issues (ALO-XXX), user reports, or architectural decisions.
Include enough background that a reader with NO conversation history understands the problem.

## Current State

What exists today. Specific file paths, current behavior, relevant code patterns.
This section prevents a fresh session from re-investigating what you already know.

## Goal

Concrete, measurable outcome. What does "done" look like?

## Approach

High-level strategy. Why this approach over alternatives?
If there were tradeoffs or rejected alternatives, mention them briefly.

## Implementation Steps

Ordered sequence. Each step should be independently completable.

### Step 1: [Action]
- **Files**: `path/to/file.py` (lines ~XX-YY)
- **What**: Specific change description
- **Why**: Reason this step is needed
- **Depends on**: Step N (if applicable)

### Step 2: [Action]
...

## Testing Strategy

- Unit tests: what to test, where to add them
- Integration tests: what scenarios to cover
- Manual verification: how to confirm it works end-to-end

## Risks & Open Questions

- Known unknowns
- Assumptions that need validation
- Potential blockers

## Affected Systems

| Repo | Files/Areas | Nature of Change |
|------|-------------|-----------------|
| alora-backend | `path/to/...` | New endpoint |
| alora-frontend | `path/to/...` | New component |

## Acceptance Criteria

- [ ] Criterion 1 (testable)
- [ ] Criterion 2 (testable)
- [ ] Tests pass
- [ ] No regressions
```

### Phase 3: Create Beads Issue

After the plan is written, create a tracking issue:

```bash
bd create "[Feature/Task Name]" \
  --description "Plan: alora-docs/plans/YYYY-MM-DD-descriptive-name.md

[2-3 sentence summary of what needs to happen]" \
  --acceptance "[Copy from plan's acceptance criteria]" \
  --context "[Business context, Linear refs, who requested it]" \
  --estimate [minutes] \
  --deps "[any blocking issues]"
```

**If the work has sub-tasks**, create child issues:

```bash
# Parent issue (the overall feature)
bd create "Import files: full lifecycle management" \
  --description "Plan: alora-docs/plans/2026-04-05-import-files.md" \
  --acceptance "Buyer can view, approve, and track import files end-to-end"

# Child issues (individual steps)
bd create "Import files: backend data model" \
  --deps "alora-xxx" \
  --description "Step 1 from plan. Create ImportFile model, migration, CRUD endpoints." \
  --acceptance "Model exists, migration runs, GET/POST/PATCH endpoints work" \
  --estimate 180

bd create "Import files: frontend list view" \
  --deps "alora-yyy" \
  --description "Step 2 from plan. Depends on backend endpoints being ready." \
  --acceptance "List view shows import files with status, filtering, pagination" \
  --estimate 120
```

### Phase 4: Validate

Before handing off or starting implementation:

1. **Re-read the plan** as if you have no context — does it stand alone?
2. **Check file paths** — do all referenced files actually exist?
3. **Check dependencies** — are beads issues linked correctly?
4. **Inform the user** — summarize what was created and suggest next steps

## Resuming From a Plan

When a session starts and the user references existing work:

1. Read the plan doc: `alora-docs/plans/YYYY-MM-DD-*.md`
2. Check beads state: `bd show <issue-id>` — read notes for progress
3. Check git state: `git log --oneline -10` in affected repos
4. Resume from where the notes/commits indicate

## Compaction Safety

The plan + beads issue together form a **compaction-safe resumption point**:

- **Plan doc** → full context, approach, file paths (survives any compaction)
- **Beads issue** → current state, progress notes, dependencies (injected via `bd prime`)
- **Git commits** → what's actually been implemented

If compaction happens mid-work:
1. The beads issue and plan doc persist on disk
2. `bd prime` re-injects issue context on next session/compaction
3. The plan doc has everything needed to continue

## Anti-Patterns

- **Don't write vague plans** — "implement the feature" is not a plan. Be specific about files and changes.
- **Don't skip the research phase** — plans based on assumptions lead to rework
- **Don't create plans for trivial work** — a one-file bug fix doesn't need a plan doc
- **Don't forget to update** — if the approach changes during implementation, update the plan doc and add a beads note
