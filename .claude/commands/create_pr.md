Create a pull request for the current branch following project standards.

## Your Task

Based on the user's input: "$ARGUMENTS"

The input can be:
- Empty (auto-generate from commits)
- A brief description to guide the PR summary
- An issue number to link (e.g., `#12` or `closes #12`)

## PR Title Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

### Types

| Type | Use Case |
|------|----------|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes nor adds |
| `test` | Adding or updating tests |
| `chore` | Maintenance (deps, CI, config) |

### Scopes

Derive from component labels or changed files:

| Scope | Maps To |
|-------|---------|
| `workflow` | `app/agents/` |
| `llm` | `app/services/llm/` |
| `ui` | `app/chat/` |
| `api` | `app/api/` |
| `tools` | `app/tools/` |
| `db` | `app/models/`, migrations |
| `config` | `app/config/` |
| `infra` | `infrastructure/`, `.github/` |
| `docs` | `docs/` |

**Examples:**
- `feat(tools): add web search capability`
- `fix(workflow): prevent infinite loop in error handling`
- `docs(api): add endpoint documentation`
- `refactor(llm): extract prompt templates`

## PR Body Format

```markdown
## Summary
Brief description of what this PR does (1-3 bullet points).

## Changes
- Specific change 1
- Specific change 2
- Specific change 3

## Testing
How was this tested? What should reviewers verify?

## Checklist
- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make check`)
- [ ] Documentation updated (if applicable)

Closes #<issue-number>
```

## Process

### Step 1: Gather Context

```bash
# Get current branch name
git branch --show-current

# Check if branch tracks remote
git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null

# Get commits since diverging from main
git log main..HEAD --oneline

# Get full diff for analysis
git diff main...HEAD --stat
```

### Step 2: Analyze Changes

From the branch name and commits, determine:
- **Type**: From branch prefix (`feat/` → `feat`, `fix/` → `fix`)
- **Scope**: From changed files or branch name
- **Issue number**: From branch name (e.g., `feat/12-...` → #12)

### Step 3: Check Prerequisites

```bash
# Ensure all changes are committed
git status --porcelain

# Ensure branch is pushed
git rev-parse --abbrev-ref --symbolic-full-name @{u}
```

If changes aren't committed, prompt user to commit first.
If branch isn't pushed, push with upstream tracking:
```bash
git push -u origin <branch-name>
```

### Step 4: Generate PR Content

Based on commits and diff:
1. Write a concise summary (what and why)
2. List specific changes
3. Describe testing approach
4. Link to issue if applicable

### Step 5: Create PR

```bash
gh pr create \
  --title "<type>(<scope>): <description>" \
  --body "$(cat <<'EOF'
## Summary
- Brief description of changes

## Changes
- Change 1
- Change 2

## Testing
Description of testing performed.

## Checklist
- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make check`)
- [ ] Documentation updated (if applicable)

Closes #<issue-number>
EOF
)"
```

## Example Workflow

**Current branch:** `feat/12-web-search-capability`

**Commits:**
```
a1b2c3d feat(tools): implement web search service
d4e5f6g feat(tools): add configuration for web search
g7h8i9j test(tools): add web search integration tests
```

**Generated PR:**

**Title:** `feat(tools): add web search capability`

**Body:**
```markdown
## Summary
- Adds web search capability using GPT-4.1 Responses API
- Includes configuration flag and usage tracking

## Changes
- Add `WebSearchService` in `app/tools/web_search.py`
- Add web search configuration to `app/config/settings.py`
- Add integration tests for web search functionality
- Update documentation with web search usage

## Testing
- Unit tests for WebSearchService
- Integration tests with mocked API responses
- Manual testing with live API

## Checklist
- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make check`)
- [ ] Documentation updated (if applicable)

Closes #12
```

## Edge Cases

### No Commits on Branch
If the branch has no commits ahead of main:
- Inform the user there's nothing to create a PR for
- Suggest making changes first

### Branch Not Pushed
If the branch isn't pushed to remote:
- Automatically push with `-u` flag
- Then create the PR

### PR Already Exists
If a PR already exists for this branch:
- Show the existing PR URL
- Offer to open it in browser

### Draft PR
If the user wants a draft PR, add `--draft` flag:
```bash
gh pr create --draft ...
```

### Multiple Issues
If the PR addresses multiple issues:
```markdown
Closes #12
Closes #15
```

## Post-Creation

After successful PR creation, display:
```
Created PR: https://github.com/owner/repo/pull/XX

Title: feat(tools): add web search capability
Base: main ← feat/12-web-search-capability

Next steps:
1. Review the PR description
2. Request reviewers if needed: gh pr edit --add-reviewer @username
3. Monitor CI checks: gh pr checks
```
