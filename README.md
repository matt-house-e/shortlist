# Agent Template

A production-ready template for building multi-agent conversational systems using **Chainlit** and **LangGraph**.

## Features

- **Chainlit** chat interface with authentication
- **LangGraph** workflow orchestration
- **PostgreSQL** database with Alembic migrations
- **S3** file storage (LocalStack for development)
- **Terraform** infrastructure as code for AWS
- **GitHub Actions** CI/CD pipelines
- **MkDocs** documentation

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker & Docker Compose

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/agent-template.git
   cd agent-template
   ```

2. **Install dependencies**
   ```bash
   uv sync --group dev
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Start services**
   ```bash
   make up        # Start PostgreSQL & LocalStack
   make db-migrate  # Run database migrations
   ```

5. **Run development server**
   ```bash
   make dev
   ```

6. **Open in browser**
   ```
   http://localhost:8000
   ```

## Project Structure

```
agent-template/
├── app/                    # Application code
│   ├── agents/             # LangGraph workflow & nodes
│   ├── chat/               # Chainlit handlers
│   ├── models/             # Pydantic models
│   ├── services/           # External integrations
│   ├── config/             # Configuration
│   └── auth/               # Authentication
├── infrastructure/         # Terraform IaC
├── tests/                  # Test suite
├── docs/                   # Documentation
└── ...
```

## Development

| Command | Description |
|---------|-------------|
| `make dev` | Start Chainlit dev server |
| `make up` | Start Docker services |
| `make down` | Stop Docker services |
| `make test` | Run tests |
| `make check` | Lint & format check |
| `make docs` | Serve documentation |

## Documentation

Full documentation available at `make docs` or in the `docs/` directory.

## License

MIT
