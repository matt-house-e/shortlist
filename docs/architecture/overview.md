# Architecture Overview

## Components

- **Chainlit** - Chat interface
- **LangGraph** - Workflow orchestration
- **PostgreSQL** - Database
- **S3** - File storage

## Workflow

```
User → Chainlit → Router Node → Agent Node → Response
```
