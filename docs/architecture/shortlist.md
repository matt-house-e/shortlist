# Shortlist Architecture Overview

This document provides a high-level onboarding guide for engineers joining the Shortlist project.

## System Overview

Shortlist is an AI-powered product research assistant that helps users find and compare products through conversation. Users describe what they want to buy, and the system builds a curated comparison table through a conversational workflow.

### Three-Phase Flow

The system operates through three distinct phases:

```
INTAKE → RESEARCH → ADVISE
   ↑         ↑         │
   └─────────┴─────────┘
      (refinement loops)
```

1. **INTAKE** - Gather requirements through multi-turn conversation
2. **RESEARCH** - Find product candidates and build comparison table
3. **ADVISE** - Present recommendations and handle refinement

### Core Technologies

| Component | Technology |
|-----------|------------|
| Chat UI | Chainlit |
| Workflow Engine | LangGraph |
| Database | PostgreSQL |
| LLM Provider | OpenAI (GPT-4.1) |
| Web Search | OpenAI Responses API |

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                         User                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Chat UI (Chainlit)                           │
│                   app/chat/handlers.py                          │
│  - Message handling                                             │
│  - ProductTable rendering                                       │
│  - HITL action buttons                                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Workflow (LangGraph)                           │
│               app/agents/workflow.py                            │
│                                                                 │
│  ┌─────────┐    ┌──────────┐    ┌─────────┐                    │
│  │ INTAKE  │───▶│ RESEARCH │───▶│ ADVISE  │                    │
│  └─────────┘    └──────────┘    └─────────┘                    │
│       ▲              ▲               │                          │
│       └──────────────┴───────────────┘                          │
│                 (refinement)                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Services                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐       │
│  │ LLMService  │  │   Lattice   │  │ SearchStrategy    │       │
│  │ (llm.py)    │  │(lattice.py) │  │(search_strategy.py)│      │
│  └─────────────┘  └─────────────┘  └───────────────────┘       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External APIs                                │
│  - OpenAI (GPT-4.1, web search)                                │
│  - Lattice (product enrichment)                                │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
app/
├── agents/              # LangGraph workflow nodes
│   ├── intake.py        # INTAKE node - gather user requirements
│   ├── research.py      # RESEARCH node - orchestrate find & enrich
│   ├── research_explorer.py  # Web search & candidate discovery
│   ├── research_enricher.py  # Lattice enrichment logic
│   ├── research_table.py     # Living table utilities
│   ├── advise.py        # ADVISE node - present recommendations
│   ├── workflow.py      # Graph definition & orchestration
│   └── prompts/         # YAML prompt templates
│       ├── intake.yaml
│       ├── explorer.yaml
│       ├── field_generation.yaml
│       └── search_strategy.yaml
│
├── chat/                # Chainlit handlers (UI entry point)
│   ├── handlers.py      # Main message handling & auth
│   ├── citations.py     # Citation formatting utilities
│   ├── hitl_actions.py  # HITL button handling
│   ├── starters.py      # Welcome screen prompts
│   └── table_rendering.py  # Table display & CSV export
│
├── config/              # Pydantic settings
│   └── settings.py      # Environment configuration
│
├── models/              # State schema & domain models
│   ├── state.py         # AgentState (fat state pattern)
│   └── schemas/
│       ├── base.py      # BaseSchema, TimestampedSchema
│       └── shortlist.py # Domain models (Candidate, ComparisonTable)
│
├── services/            # Business logic & external integrations
│   ├── llm.py           # LLM abstraction (OpenAI, Anthropic)
│   ├── lattice.py       # Lattice enrichment service
│   ├── search_strategy.py  # Query generation service
│   ├── field_generation.py # Dynamic field generation
│   ├── table_rendering.py  # ProductTable props preparation
│   └── openai_enrichment_chain.py  # OpenAI-based enrichment
│
├── auth/                # Authentication
│   ├── password_auth.py # Password-based auth
│   └── oauth.py         # OAuth/SSO provider (placeholder)
│
└── utils/               # Utilities
    ├── logger.py        # Logging configuration
    ├── sanitization.py  # Input sanitization
    ├── hitl.py          # HITL message parsing utilities
    └── retry.py         # Retry decorators for external calls
```

## Data Flow

### Normal Flow

```
1. User sends message
      │
      ▼
2. Chainlit on_message()
      │
      ▼
3. process_message_with_state()
      │
      ▼
4. Router node determines phase
      │
      ├── phase=intake  ──▶ intake_node()
      ├── phase=research ──▶ research_node()
      └── phase=advise  ──▶ advise_node()
            │
            ▼
5. Node processes & returns Command
      │
      ▼
6. State updates via Command.update
      │
      ▼
7. Response rendered to UI
```

### HITL (Human-in-the-Loop) Flow

```
1. Node reaches checkpoint
      │
      ▼
2. Returns with action_choices & awaiting_*_confirmation flag
      │
      ▼
3. Chainlit renders action buttons
      │
      ▼
4. User clicks button
      │
      ▼
5. on_hitl_action() creates synthetic message: [HITL:checkpoint:choice]
      │
      ▼
6. Router directs to appropriate node based on checkpoint type
      │
      ▼
7. Node parses HITL message and continues
```

## Core Concepts

### Fat State Pattern

All workflow data lives in a single `AgentState` TypedDict (`models/state.py:11`). This simplifies debugging and makes state transitions explicit.

Key state sections:
- **Message history** - LangGraph's `add_messages` reducer
- **Workflow control** - `current_phase`, `current_node`
- **User context** - `user_id`, `session_id`
- **Domain data** - `user_requirements`, `living_table`, `candidates`
- **HITL control** - `awaiting_*_confirmation`, `action_choices`, `pending_*`

### HITL Checkpoints

Three checkpoint types pause workflow for user confirmation:

| Checkpoint | Phase | Trigger | Choices |
|------------|-------|---------|---------|
| `requirements` | INTAKE | Product type identified | "Ready to Search" |
| `fields` | RESEARCH | Explorer found candidates | "Enrich Now", "Modify Fields" |
| `intent` | ADVISE | User wants action | "Yes, proceed", "No, let me clarify" |

### Living Table Architecture

The `ComparisonTable` model (`models/schemas/shortlist.py`) is the single source of truth for product data:

- **Rows** - Products with cell data per field
- **Fields** - Dynamic field definitions (standard, category, qualification)
- **Cell Status** - PENDING, ENRICHED, FAILED, FLAGGED

This enables:
- Incremental enrichment (only enrich PENDING cells)
- Adding new fields without re-enriching existing data
- Tracking enrichment failures per cell

### Incremental Enrichment

When users request new comparison fields:

1. ADVISE detects `new_fields` intent
2. Sets `requested_fields` in state
3. Routes to RESEARCH with `need_new_search=False`
4. RESEARCH adds fields to `living_table` (marks cells PENDING)
5. Enriches only new cells via Lattice
6. Returns to ADVISE with updated table

## Entry Points

| Purpose | Location |
|---------|----------|
| Chat session start | `chat/handlers.py:150` - `on_chat_start()` |
| Message handling | `chat/handlers.py:175` - `on_message()` |
| HITL action handling | `chat/hitl_actions.py:65` - `on_hitl_action()` |
| Workflow creation | `agents/workflow.py:101` - `create_workflow()` |
| Message processing | `agents/workflow.py:221` - `process_message_with_state()` |
| State schema | `models/state.py:11` - `AgentState` |

## Key Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `agents/workflow.py` | 311 | Graph definition, routing, message processing |
| `agents/intake.py` | 308 | Requirement gathering, conversational flow |
| `agents/research.py` | 420 | Research orchestrator (3 execution paths) |
| `agents/research_explorer.py` | 621 | Web search & candidate discovery |
| `agents/research_enricher.py` | 117 | Lattice enrichment logic |
| `agents/research_table.py` | 106 | Living table utilities |
| `agents/advise.py` | 440 | Recommendation presentation, intent detection |
| `chat/handlers.py` | 292 | Main Chainlit handlers |
| `chat/hitl_actions.py` | 174 | HITL button handling |
| `chat/table_rendering.py` | 228 | Table display & CSV export |
| `models/state.py` | 194 | Central state schema |
| `models/schemas/shortlist.py` | 513 | Domain models (ComparisonTable, etc.) |
| `services/llm.py` | 420 | LLM abstraction layer |

## Node Functions

Each node follows this pattern:

```python
async def node_name(state: AgentState) -> Command:
    """
    Node docstring explaining purpose.
    """
    # 1. Check for HITL action
    if messages and last_message.startswith("[HITL:"):
        # Handle HITL choice
        ...

    # 2. Main processing logic
    ...

    # 3. Return Command with state updates and routing
    return Command(
        update={
            "messages": [AIMessage(content=response)],
            "current_phase": "next_phase",
            ...
        },
        goto="next_node",  # or "__end__" to wait for user
    )
```

## Service Instantiation Patterns

The codebase uses multiple patterns for service instantiation:

| Pattern | Example | Used By |
|---------|---------|---------|
| `@lru_cache` | `get_llm_service()` | Main LLM service |
| Manual singleton | `get_search_strategy_service()` | Search strategy |
| Fresh instance | `LatticeService()` | Lattice enrichment |
| Direct instantiation | `LLMService(settings)` | INTAKE, RESEARCH |

## Development Commands

```bash
make dev      # Start Chainlit dev server
make up       # Start Docker services (DB, LocalStack)
make test     # Run pytest suite
make check    # Run ruff lint & format
```

## Related Documentation

- `docs/architecture/code-reference.md` - Detailed class/function reference
- `SPEC.md` - Full template patterns
- `SHORTLIST_SPEC.md` - State schema & phases
- `docs/development/github-standards.md` - PR/issue workflow
