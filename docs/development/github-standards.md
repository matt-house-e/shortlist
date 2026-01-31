# GitHub Standards

This document defines the standards for issue management, pull requests, and collaboration on this project.

## Why Standards Matter

Consistent standards enable:
- **Filtering & Search**: Find issues by type, priority, or component
- **Automation**: GitHub Actions can respond to labels
- **Visual Hierarchy**: Quickly scan issue lists
- **Clear Communication**: Everyone understands issue status at a glance

---

## Issue Management

### Issue Types

| Type | Use Case |
|------|----------|
| **Epic** | Multi-sprint initiative spanning multiple stories |
| **Story** | User-facing feature with clear acceptance criteria |
| **Task** | Technical work that doesn't directly add user value |
| **Bug** | Defect in existing functionality |
| **Spike** | Research or investigation with timeboxed output |
| **Tool** | LLM tool/function implementation |

### Issue Title Format

```
[Type]: [Component] Brief description
```

**Examples:**
- `[Story]: [UI] Add conversation history sidebar`
- `[Bug]: [Workflow] Agent gets stuck in infinite loop`
- `[Tool]: [Tools] Add web search capability`
- `[Spike]: [LLM] Evaluate Claude vs GPT-4 for summarization`

### Issue Body Template

```markdown
## Context
Why does this issue exist? What problem does it solve?

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Technical Notes
Implementation hints, constraints, or dependencies.

## Definition of Done
- [ ] Code complete and tested
- [ ] Tests pass locally and in CI
- [ ] Documentation updated (if applicable)
- [ ] PR reviewed and approved
```

---

## Label Taxonomy

### Type Labels

| Label | Color | Description |
|-------|-------|-------------|
| `type:epic` | `#0052CC` | Multi-sprint initiative |
| `type:story` | `#0075CA` | User-facing feature |
| `type:task` | `#4C9AFF` | Technical work |
| `type:bug` | `#FF5630` | Defect |
| `type:spike` | `#6554C0` | Research/investigation |
| `type:tool` | `#5319E7` | LLM tool implementation |

### Priority Labels

| Label | Color | Description |
|-------|-------|-------------|
| `priority:critical` | `#FF5630` | Production down, data loss risk |
| `priority:high` | `#FF7452` | Blocking other work |
| `priority:medium` | `#FFAB00` | Important but not blocking |
| `priority:low` | `#FFC400` | Nice to have |

### Component Labels

| Label | Color | Description |
|-------|-------|-------------|
| `component:workflow` | `#00B8D9` | LangGraph nodes and state |
| `component:llm` | `#00B8D9` | LLM service and prompts |
| `component:ui` | `#00B8D9` | Chainlit interface |
| `component:api` | `#00B8D9` | FastAPI endpoints |
| `component:service` | `#00B8D9` | Business logic services |
| `component:database` | `#00B8D9` | PostgreSQL and models |
| `component:tools` | `#00B8D9` | LLM tools/functions |
| `component:testing` | `#00B8D9` | Test infrastructure |
| `component:infra` | `#00B8D9` | Docker, CI/CD, Terraform |
| `component:docs` | `#00B8D9` | Documentation |

---

## Pull Request Standards

### PR Title Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `refactor` - Code change that neither fixes nor adds
- `test` - Adding or updating tests
- `chore` - Maintenance (deps, CI, etc.)

**Examples:**
- `feat(workflow): add retry logic to LLM calls`
- `fix(ui): resolve message rendering race condition`
- `docs(api): add endpoint documentation`

### PR Body Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- Change 1
- Change 2

## Testing
How was this tested?

## Checklist
- [ ] Tests pass
- [ ] Linting passes (`make check`)
- [ ] Documentation updated (if applicable)

Closes #<issue-number>
```

---

## Branch Strategy

This project uses **GitHub Flow**:

1. `main` is always deployable
2. Create feature branches from `main`
3. Open PR when ready for review
4. Merge to `main` after approval
5. Deploy from `main`

### Branch Naming

```
<type>/<issue-number>-<brief-description>
```

**Examples:**
- `feat/12-web-search-tool`
- `fix/45-message-ordering`
- `spike/23-evaluate-vector-db`

---

## Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Examples:**
```
feat(tools): add web search capability

Implements web search using GPT-4.1 Responses API.
Includes configuration flag and usage tracking.

Closes #12
```

```
fix(workflow): prevent infinite loop in error handling

The agent was retrying failed LLM calls indefinitely.
Added max_retries configuration with exponential backoff.
```

---

## Claude Code Integration

### Creating Issues

Use the `/create_issue` slash command:
```
/create_issue Add web search capability using GPT-4.1 Responses API
```

Claude will:
1. Determine appropriate type, priority, and components
2. Generate acceptance criteria
3. Create the issue with proper labels

### Creating PRs

Use the `/create_pr` slash command after completing work.

### Creating Branches

Use the `/create_branch` slash command:
```
/create_branch 12
```

Creates a properly named branch for issue #12.
