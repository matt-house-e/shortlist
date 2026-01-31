Create a feature branch from main with conventional naming.

## Your Task

Based on the user's input: "$ARGUMENTS"

The input can be:
- An issue number (e.g., `12` or `#12`)
- A description (e.g., `add web search capability`)
- Both (e.g., `12 add web search`)

## Branch Naming Convention

```
<type>/<issue-number>-<brief-description>
```

### Type Prefixes

Map from issue type labels to branch prefixes:

| Issue Label | Branch Prefix | Use Case |
|-------------|---------------|----------|
| `type:story` | `feat/` | New user-facing features |
| `type:tool` | `feat/` | New LLM tools (tools are features) |
| `type:epic` | `feat/` | Epic-level work |
| `type:bug` | `fix/` | Bug fixes |
| `type:task` | `chore/` | Technical tasks, maintenance |
| `type:spike` | `spike/` | Research and investigation |
| (no type) | `feat/` | Default to feature |

### Description Rules

- Use lowercase letters only
- Replace spaces with hyphens
- Keep it brief (2-4 words max)
- Remove articles (a, an, the)
- Remove filler words

**Examples:**
- `feat/12-web-search-tool`
- `fix/45-message-ordering`
- `spike/23-evaluate-vector-db`
- `chore/67-update-dependencies`

## Process

### Step 1: Parse Input

If an issue number is provided:
```bash
# Fetch issue details
gh issue view <number> --json title,labels
```

Extract:
- Issue title for description
- Labels to determine branch type

### Step 2: Ensure Clean State

```bash
# Check for uncommitted changes
git status --porcelain
```

If there are uncommitted changes, warn the user and ask how to proceed:
- Stash changes
- Commit changes first
- Abort

### Step 3: Update Main

```bash
# Ensure we're on latest main
git checkout main
git pull origin main
```

### Step 4: Create Branch

```bash
# Create and switch to new branch
git checkout -b <branch-name>
```

### Step 5: Set Upstream (Optional)

If the user wants to push immediately:
```bash
git push -u origin <branch-name>
```

## Example Workflow

**Input:** `12`

**Steps:**
1. Fetch issue #12: `[Tool]: [Tools] Add web search capability`
2. Labels include `type:tool` → use `feat/` prefix
3. Generate description: `web-search-capability`
4. Final branch name: `feat/12-web-search-capability`
5. Create branch from main

**Output:**
```
Created branch: feat/12-web-search-capability
Based on issue #12: [Tool]: [Tools] Add web search capability

Next steps:
1. Make your changes
2. Commit with: git commit -m "feat(tools): add web search capability"
3. Push with: git push -u origin feat/12-web-search-capability
4. Create PR with: /create_pr
```

## Edge Cases

### No Issue Number
If only a description is provided, ask the user to confirm the branch type:
- `feat/` for new functionality
- `fix/` for bug fixes
- `chore/` for maintenance
- `spike/` for research

### Issue Not Found
If the issue number doesn't exist, inform the user and offer to:
- Create the issue first with `/create_issue`
- Proceed without an issue number

### Branch Already Exists
If the branch name already exists:
- Offer to switch to the existing branch
- Offer to create with a suffix (e.g., `feat/12-web-search-v2`)
