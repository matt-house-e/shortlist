# Agent Template - Claude Code Context

## Project Overview

This is a **multi-agent conversational system template** built with:
- **Chainlit** - Chat interface
- **LangGraph** - Workflow orchestration
- **PostgreSQL** - Database
- **AWS (ECS Fargate)** - Production deployment

## Directory Structure

```
app/                    # Main application code
├── chat/               # Chainlit handlers
├── agents/             # LangGraph workflow & nodes
├── models/             # Pydantic models & state
├── services/           # External service integrations
├── config/             # Configuration management
├── auth/               # Authentication providers
└── utils/              # Utility functions

infrastructure/         # Terraform IaC
tests/                  # Test suite
docs/                   # MkDocs documentation
```

## Key Files

- `app/agents/workflow.py` - LangGraph graph definition
- `app/models/state.py` - Central state schema
- `app/chat/handlers.py` - Chainlit entry point
- `app/config/settings.py` - Pydantic settings

## Development Commands

```bash
make dev              # Start Chainlit dev server
make up               # Start Docker services (DB, LocalStack)
make test             # Run tests
make check            # Lint & format check
make db-migrate       # Run migrations
make docs             # Serve documentation
```

## Architecture Patterns

### Fat State Pattern
All workflow data lives in `AgentState` (app/models/state.py). This simplifies debugging and state inspection.

### Node Functions
Agent logic is pure functions that return `Command` objects for routing:
```python
async def agent_node(state: AgentState) -> Command:
    return Command(update={...}, goto="next_node")
```

### Service Layer
External dependencies are abstracted behind service classes in `app/services/`.

## Testing

- Unit tests: `tests/agents/`, `tests/services/`, `tests/models/`
- Integration tests: `tests/integration/`
- Fixtures in `tests/conftest.py`

## Environment

- Python 3.12+
- PostgreSQL 16
- LocalStack for S3 emulation (development)
- Configuration via `.env` file

## Deployment

- Production: AWS ECS Fargate
- Infrastructure: Terraform modules in `infrastructure/`
- CI/CD: GitHub Actions in `.github/workflows/`
