Create a GitHub issue following the project's GitHub standards.

## Your Task

Based on the user's description: "$ARGUMENTS"

1. **Determine Issue Type** (one of):
   - `epic` - Multi-sprint initiative spanning multiple stories
   - `story` - User-facing feature with clear acceptance criteria
   - `task` - Technical work that doesn't directly add user value
   - `bug` - Defect in existing functionality
   - `spike` - Research or investigation with timeboxed output
   - `tool` - LLM tool/function implementation

2. **Determine Priority** (one of):
   - `critical` - Production down, data loss risk
   - `high` - Blocking other work
   - `medium` - Important but not blocking (default)
   - `low` - Nice to have

3. **Determine Components** (one or more):
   - `workflow` - LangGraph nodes and state (`app/agents/`)
   - `llm` - LLM service and prompts (`app/services/llm/`)
   - `ui` - Chainlit interface (`app/chat/`)
   - `api` - FastAPI endpoints (`app/api/`)
   - `service` - Business logic services (`app/services/`)
   - `database` - PostgreSQL and models (`app/models/`)
   - `tools` - LLM tools/functions (`app/tools/`)
   - `testing` - Test infrastructure (`tests/`)
   - `infra` - Docker, CI/CD, Terraform (`infrastructure/`, `.github/`)
   - `docs` - Documentation (`docs/`)

## Issue Title Format

```
[Type]: [Component] Brief description
```

Examples:
- `[Story]: [UI] Add conversation history sidebar`
- `[Bug]: [Workflow] Agent gets stuck in infinite loop`
- `[Tool]: [Tools] Add web search capability`

## Issue Body Format

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

## Create the Issue

Use `gh issue create` with:
- `--title` - Formatted title
- `--body` - Full body content (use HEREDOC)
- `--label` - One type label, one priority label, one or more component labels

Example:
```bash
gh issue create \
  --title "[Tool]: [Tools] Add web search capability" \
  --label "type:tool" \
  --label "priority:medium" \
  --label "component:tools" \
  --label "component:llm" \
  --body "$(cat <<'EOF'
## Context
...

## Acceptance Criteria
...

## Technical Notes
...

## Definition of Done
- [ ] Code complete and tested
- [ ] Tests pass locally and in CI
- [ ] Documentation updated (if applicable)
- [ ] PR reviewed and approved
EOF
)"
```

After creating, display the issue URL to the user.
