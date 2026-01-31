# Agent Template - Live Specification

> **Status**: Active Development
> **Version**: 0.1.0
> **Last Updated**: 2025-01-23

---

## Overview

A production-ready template for building multi-agent conversational systems using **Chainlit** (chat interface) and **LangGraph** (workflow orchestration). This template captures battle-tested patterns from production deployments, providing a skeleton structure for rapid development of similar systems.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        CHAINLIT INTERFACE                        │
│  (Chat UI, File Uploads, Authentication, Session Management)    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH WORKFLOW                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  START NODE  │───▶│  AGENT NODE  │───▶│   END NODE   │      │
│  │  (Router)    │    │  (Your Logic)│    │  (Cleanup)   │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                              │                                   │
│                    ┌─────────┴─────────┐                        │
│                    ▼                   ▼                        │
│            ┌──────────────┐    ┌──────────────┐                 │
│            │  TOOL NODES  │    │ HUMAN INPUT  │                 │
│            │  (Optional)  │    │  (Optional)  │                 │
│            └──────────────┘    └──────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                             │
│  ┌─────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │   LLM   │  │  Knowledge  │  │ External │  │   Database   │  │
│  │ Service │  │   Service   │  │   APIs   │  │   Service    │  │
│  └─────────┘  └─────────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Chat Interface** | Chainlit | Real-time chat UI, file uploads, auth |
| **Workflow Engine** | LangGraph | Multi-agent orchestration, state management |
| **LLM Integration** | LangChain + OpenAI/Anthropic | LLM abstraction, structured outputs |
| **Data Validation** | Pydantic v2 | Type safety, schema validation |
| **Database** | PostgreSQL + asyncpg | Persistent storage, async queries |
| **Migrations** | Alembic | Database schema versioning |
| **File Storage** | S3 (LocalStack for dev) | File uploads, attachments |
| **Infrastructure** | Terraform | AWS IaC (ECS Fargate, RDS, ALB) |
| **Container** | Docker | Reproducible builds, deployment |
| **CI/CD** | GitHub Actions | Automated testing, deployment |
| **Documentation** | MkDocs Material | Developer documentation |
| **Package Management** | uv + pyproject.toml | Fast, modern Python tooling |

---

## Directory Structure

```
agent-template/
│
├── .claude/                      # Claude Code configuration
│   ├── settings.local.json       # Permissions & MCP servers
│   └── commands/                 # Custom slash commands
│       ├── create_pr.md
│       ├── create_issue.md
│       └── create_branch.md
│
├── .github/                      # GitHub configuration
│   └── workflows/
│       ├── ci.yml                # Test & lint on PR
│       ├── deploy.yml            # Production deployment
│       └── sync-kb.yml           # Knowledge base sync (optional)
│
├── app/                          # Main application code
│   ├── __init__.py
│   ├── chat/                     # Chainlit integration
│   │   ├── __init__.py
│   │   └── handlers.py           # Chat event handlers
│   │
│   ├── agents/                   # LangGraph workflow & nodes
│   │   ├── __init__.py
│   │   ├── workflow.py           # Graph definition & orchestration
│   │   ├── router.py             # Entry point routing node
│   │   ├── agent.py              # Main agent node (placeholder)
│   │   └── prompts/              # Agent prompt templates
│   │       └── agent.yaml
│   │
│   ├── models/                   # Pydantic models
│   │   ├── __init__.py
│   │   ├── state.py              # LangGraph state schema
│   │   └── schemas/              # Domain-specific schemas
│   │       ├── __init__.py
│   │       └── base.py           # Base schema utilities
│   │
│   ├── services/                 # External service integrations
│   │   ├── __init__.py
│   │   ├── llm.py                # LLM abstraction layer
│   │   └── knowledge.py          # Knowledge base service (optional)
│   │
│   ├── config/                   # Configuration management
│   │   ├── __init__.py
│   │   └── settings.py           # Pydantic settings
│   │
│   ├── auth/                     # Authentication providers
│   │   ├── __init__.py
│   │   ├── password_auth.py      # Simple password auth
│   │   └── oauth.py              # OAuth/SSO (placeholder)
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── logger.py             # Logging configuration
│   │   └── sanitization.py       # Input validation
│   │
│   ├── api/                      # REST API (optional, placeholder)
│   │   └── __init__.py
│   │
│   └── data/                     # Static data files
│       └── .gitkeep
│
├── dashboard/                    # Analytics dashboard (placeholder)
│   └── .gitkeep
│
├── docs/                         # MkDocs documentation
│   ├── index.md
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── langgraph-workflow.md
│   │   └── decisions.md          # Architecture Decision Records
│   ├── development/
│   │   ├── getting-started.md
│   │   ├── local-setup.md
│   │   └── testing.md
│   └── deployment/
│       ├── aws-infrastructure.md
│       └── ci-cd.md
│
├── infrastructure/               # Terraform IaC
│   ├── README.md
│   ├── shared/
│   │   ├── versions.tf           # Provider versions
│   │   └── backend.tf            # S3 state backend
│   │
│   ├── modules/                  # Reusable Terraform modules
│   │   ├── vpc/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── ecs-fargate/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── rds/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── alb/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── ecr/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── cloudwatch/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── s3/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── route53/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   ├── acm-certificate/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   └── bastion/
│   │       ├── main.tf
│   │       ├── variables.tf
│   │       └── outputs.tf
│   │
│   └── environments/
│       ├── production/
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   ├── outputs.tf
│       │   └── terraform.tfvars.example
│       └── staging/
│           ├── main.tf
│           ├── variables.tf
│           ├── outputs.tf
│           └── terraform.tfvars.example
│
├── knowledgebase/                # Knowledge base management
│   ├── README.md
│   ├── export/                   # Exported documents
│   │   └── .gitkeep
│   └── scripts/
│       └── sync_vectorstore.py   # Vector store sync script
│
├── logs/                         # Application logs (gitignored)
│   └── .gitkeep
│
├── public/                       # Chainlit static assets
│   ├── avatars/
│   │   └── .gitkeep
│   ├── custom.css                # UI customization
│   ├── custom.js                 # Frontend logic
│   └── theme.json                # Color theme
│
├── scripts/                      # Utility scripts
│   ├── localstack-init.sh        # LocalStack S3 setup
│   └── rds-tunnel.sh             # Production DB tunnel
│
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures
│   ├── agents/
│   │   ├── __init__.py
│   │   └── test_workflow.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── test_llm.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── test_state.py
│   └── integration/
│       ├── __init__.py
│       └── .gitkeep
│
├── alembic/                      # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── .gitkeep
│
├── .chainlit/                    # Chainlit config (auto-generated)
│   └── .gitkeep
│
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── .python-version               # Python version (for pyenv/asdf)
├── chainlit.md                   # Chat welcome message
├── CLAUDE.md                     # Claude Code context
├── docker-compose.yml            # Local development stack
├── Dockerfile                    # Production container
├── Makefile                      # Development automation
├── mkdocs.yml                    # Documentation config
├── pyproject.toml                # Python project config
├── README.md                     # Project documentation
└── SPEC.md                       # This file
```

---

## Core Design Patterns

### 1. Fat State Pattern

All workflow data lives in a single state object, simplifying debugging and data flow:

```python
class AgentState(TypedDict):
    """Central state for the entire workflow."""
    # Message history (with LangGraph reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Workflow control
    phase: str
    current_node: str

    # User context
    user_id: str
    session_id: str

    # Domain-specific fields
    # ... add your fields here
```

### 2. Node Functions (Not Classes)

Pure functions as LangGraph nodes with Command API for routing:

```python
async def agent_node(state: AgentState) -> Command:
    """Process user input and determine next action."""
    # Your agent logic here

    return Command(
        update={"phase": "complete"},
        goto="end"
    )
```

### 3. Service Layer Abstraction

External dependencies behind clean interfaces:

```python
class LLMService:
    """Abstract LLM interactions for testability."""

    async def generate(self, messages: list) -> str:
        # Provider-agnostic LLM calls
        pass
```

### 4. Pydantic Everywhere

Type-safe data validation at all boundaries:

```python
class Settings(BaseSettings):
    """Application configuration from environment."""
    model_config = SettingsConfigDict(env_file=".env")

    openai_api_key: str
    database_url: str
    # ...
```

---

## Infrastructure Patterns

### AWS Architecture (ECS Fargate)

```
┌─────────────────────────────────────────────────────────────┐
│                         VPC                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Public Subnets                      │   │
│  │  ┌─────────────┐              ┌─────────────┐       │   │
│  │  │     ALB     │              │   Bastion   │       │   │
│  │  │  (HTTPS)    │              │   (SSH)     │       │   │
│  │  └──────┬──────┘              └─────────────┘       │   │
│  └─────────┼───────────────────────────────────────────┘   │
│            │                                                │
│  ┌─────────┼───────────────────────────────────────────┐   │
│  │         │        Private Subnets                     │   │
│  │         ▼                                            │   │
│  │  ┌─────────────┐              ┌─────────────┐       │   │
│  │  │ ECS Fargate │              │     RDS     │       │   │
│  │  │  (Chainlit) │─────────────▶│ (PostgreSQL)│       │   │
│  │  └─────────────┘              └─────────────┘       │   │
│  │                                                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │     ECR     │  │     S3      │  │ CloudWatch  │   │  │
│  │  │  (Images)   │  │  (Storage)  │  │   (Logs)    │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Terraform Module Structure

- **Modular**: Each AWS service in its own module
- **Reusable**: Same modules work across environments
- **Conditional**: Optional resources via count/for_each
- **Secure**: S3 backend with state locking

---

## Development Workflow

### Local Development

```bash
# Start all services
make up

# Run Chainlit dev server
make dev

# Access at http://localhost:8000
```

### Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Lint & format
make check
```

### Database Migrations

```bash
# Create new migration
make db-revision msg="add users table"

# Apply migrations
make db-migrate
```

### Documentation

```bash
# Serve docs locally
make docs

# Build static site
make docs-build
```

---

## Configuration

### Environment Variables

All configuration via environment variables with sensible defaults:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `CHAINLIT_AUTH_SECRET` | Session encryption key | Required |
| `LLM_MODEL` | Model to use | `gpt-4o` |
| `LLM_TEMPERATURE` | Generation temperature | `0.7` |
| `S3_BUCKET` | File storage bucket | `uploads` |
| `AUTH_METHOD` | `password` or `oauth` | `password` |

### Authentication Options

1. **Password Auth**: Simple shared password (development/testing)
2. **OAuth/SSO**: Azure AD, Google, etc. (production)

---

## Extending the Template

### Adding a New Agent Node

1. Create node function in `app/agents/`:
```python
async def my_agent_node(state: AgentState) -> Command:
    # Your logic here
    return Command(update={...}, goto="next_node")
```

2. Register in workflow graph (`app/agents/workflow.py`):
```python
graph.add_node("my_agent", my_agent_node)
graph.add_edge("router", "my_agent")
```

3. Add prompts in `app/agents/prompts/my_agent.yaml`

### Adding a New Service

1. Create service class in `app/services/`:
```python
class MyService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def do_something(self) -> Result:
        pass
```

2. Add configuration to `app/config/settings.py`

3. Inject into nodes via dependency

### Adding External Integrations

1. Add SDK to `pyproject.toml` dependencies
2. Create service wrapper in `app/services/`
3. Add configuration to settings
4. Create mock for testing

---

## CI/CD Pipeline

### Pull Request Checks

```yaml
on: [pull_request]
jobs:
  test:
    - Lint with ruff
    - Type check (optional)
    - Run pytest
    - Check coverage threshold
```

### Production Deployment

```yaml
on:
  push:
    branches: [main]
jobs:
  deploy:
    - Build Docker image
    - Push to ECR
    - Update ECS task definition
    - Deploy to Fargate
    - Verify health
```

---

## Security Considerations

- [ ] Non-root Docker user
- [ ] IAM roles (not hardcoded credentials)
- [ ] Input sanitization
- [ ] Environment-based secrets
- [ ] HTTPS everywhere (ACM certificates)
- [ ] VPC isolation (private subnets)
- [ ] Security groups (least privilege)

---

## Next Steps

1. [ ] Clone template
2. [ ] Configure `.env` from `.env.example`
3. [ ] Run `make up` to start local services
4. [ ] Run `make dev` to start Chainlit
5. [ ] Add your agent logic in `app/agents/`
6. [ ] Add your schemas in `app/models/schemas/`
7. [ ] Configure infrastructure in `infrastructure/`
8. [ ] Deploy!

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2025-01-23 | Initial template structure |
