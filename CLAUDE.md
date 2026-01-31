# Shortlist - Claude Code Context

## What This Is

Shortlist is an AI-powered product research system. Users describe what they want to buy, and it builds a curated comparison table through conversation.

- **Chat UI**: Chainlit | **Workflow**: LangGraph | **Database**: PostgreSQL
- **Three-phase flow**: INTAKE → RESEARCH → ADVISE (with refinement loop)

## Project Layout

```
app/agents/         # LangGraph workflow & nodes
app/models/state.py # AgentState (fat state pattern)
app/services/       # LLM, Lattice, external APIs
app/chat/           # Chainlit handlers
app/config/         # Pydantic settings
infrastructure/     # Terraform (AWS ECS Fargate)
tests/              # pytest suite
```

## Key Files

- `app/agents/workflow.py` - Graph definition
- `app/models/state.py` - Central state schema
- `app/config/settings.py` - Environment configuration

## Development

**Local only** - no cloud deployment yet. Use Docker Compose for all services.

```bash
make dev      # Start Chainlit dev server
make up       # Docker services (DB, LocalStack)
make test     # Run tests
make check    # Lint & format (ruff)
```

## Verification

Before committing: `make check && make test`

## Architecture Deep Dives

| Topic | Reference |
|-------|-----------|
| Full template patterns | SPEC.md |
| State schema & phases | SHORTLIST_SPEC.md |
| Node function pattern | SPEC.md:299-310 |
| Adding agent nodes | SPEC.md:458-473 |
| Adding services | SPEC.md:475-489 |

## GitHub Workflow

Use slash commands:
- `/create_branch <issue>` - Feature branch from main
- `/create_issue <desc>` - Create labeled issue
- `/create_pr` - PR with conventional commits

Full standards: `docs/development/github-standards.md`
