# Code Review Findings

This document catalogs code smells, technical debt, and proposed improvements identified during codebase review.

## Critical Issues Summary

| Issue | Location | Severity | Status |
|-------|----------|----------|--------|
| ~~Duplicate `_parse_hitl_choice()`~~ | ~~`research.py`, `advise.py`, `intake.py`~~ | ~~Medium~~ | ✅ Fixed |
| ~~Duplicate `_clear_hitl_flags()`~~ | ~~`research.py`, `advise.py`, `intake.py`~~ | ~~Medium~~ | ✅ Fixed |
| ~~Deprecated field `comparison_table` still in use~~ | ~~`state.py`, `research.py`~~ | ~~Medium~~ | ✅ Fixed |
| ~~Vestigial `phase` field (unused)~~ | ~~`state.py`~~ | ~~Low~~ | ✅ Fixed |
| ~~Large file `research.py` (1427 lines)~~ | ~~`agents/research.py`~~ | ~~High~~ | ✅ Fixed (469 lines) |
| ~~Large file `handlers.py` (723 lines)~~ | ~~`chat/handlers.py`~~ | ~~High~~ | ✅ Fixed (292 lines) |

---

## Code Smells by Category

### 1. Large Files / God Objects

**Severity: High**

#### ~~`research.py` (1427 lines)~~ ✅ FIXED

Split into focused modules:
- `research.py` (469 lines) - node orchestration only
- `research_explorer.py` (611 lines) - candidate discovery
- `research_enricher.py` (203 lines) - Lattice enrichment
- `research_table.py` (129 lines) - table utilities

#### ~~`handlers.py` (723 lines)~~ ✅ FIXED

Split into focused modules:
- `handlers.py` (292 lines) - message handling and lifecycle
- `table_rendering.py` (228 lines) - table rendering and export
- `hitl_actions.py` (174 lines) - HITL button handling
- `citations.py` (32 lines) - citation formatting
- `starters.py` (25 lines) - welcome screen starters

#### `state.py` - Borderline God Object

`AgentState` has 35+ fields. While the "fat state" pattern is intentional, some grouping could improve maintainability:
- Consider nested TypedDicts for logical groupings
- Some fields are rarely used together

---

### 2. Code Duplication

**Severity: Medium**

#### ~~HITL Parsing Functions (3 locations)~~ ✅ FIXED

Consolidated into `app/utils/hitl.py`. All agent files now import from this module.

#### ~~HITL Flag Clearing (3 locations)~~ ✅ FIXED

Consolidated into `app/utils/hitl.py`. All agent files now import from this module.

#### Response Rendering Duplication

ProductTable sending logic appears in two places with nearly identical code:

```python
# handlers.py:597-613 (in on_hitl_action)
if current_phase == "advise" and result.living_table:
    llm_service = cl.user_session.get("llm_service")
    user_requirements = None
    try:
        current_state = await workflow.aget_state(config)
        if current_state.values:
            user_requirements = current_state.values.get("user_requirements")
    except Exception:
        pass
    await send_product_table(...)

# handlers.py:687-704 (in on_message) - nearly identical
```

---

### 3. Inconsistent Service Instantiation

**Severity: Medium**

The codebase uses three different patterns for service instantiation:

| Service | Pattern | Location |
|---------|---------|----------|
| `LLMService` | `@lru_cache` singleton | `llm.py:371-374` |
| `SearchStrategyService` | Manual singleton | `search_strategy.py` |
| `LatticeService` | Fresh instance each time | `research.py:783`, `research.py:901` |
| `LLMService` | Direct instantiation | `research.py:680`, `handlers.py:491` |

This inconsistency makes it unclear:
- Which services are thread-safe
- Whether service state persists across calls
- How to properly mock services in tests

---

### 4. State Schema Issues ✅ FIXED

**Severity: Medium**

#### ~~Duplicate Phase Fields~~ ✅ FIXED

Removed vestigial `phase` field. Only `current_phase` is now used:

```python
# state.py:110
current_phase: str  # intake, research, advise
```

#### ~~Deprecated Field Still In Use~~ ✅ FIXED

Removed `comparison_table` field and all usages:
- Removed from `state.py` schema and `create_initial_state()`
- Removed `enricher_step()` function from `research_enricher.py`
- Removed `build_field_definitions_list()` from `research_table.py`
- Updated `research.py` to only use `living_table`
- Updated `advise.py` to only use `living_table` (removed fallback)

---

### 5. Error Handling Issues

**Severity: Medium**

#### Silent Exception Handling

```python
# handlers.py:544-545
except Exception:
    pass  # Fall back to default
```

This silently swallows errors when getting product name, making debugging difficult.

#### Bare `except Exception` Without Specific Handling

Multiple locations catch `Exception` without handling specific error types:

```python
# research.py:1144
except Exception:
    logger.exception("RESEARCH enrichment error")
    return Command(...)

# advise.py:481
except Exception:
    logger.exception("ADVISE error")
    return Command(...)
```

While logging is present, there's no retry logic or specific handling for transient errors vs. permanent failures.

#### No Retry Logic for External Services

Critical external service calls (Lattice, OpenAI) have no retry logic:
- `llm.py:290` - OpenAI Responses API call
- `lattice.py` - Lattice enrichment calls
- `research.py:385-388` - Web search calls

---

### 6. Coupling Issues

**Severity: Low-Medium**

#### Direct OpenAI Client Bypasses LangChain

```python
# llm.py:230
from openai import AsyncOpenAI
...
client = AsyncOpenAI(api_key=self.settings.openai_api_key)
```

The `generate_with_web_search` method bypasses the LangChain abstraction entirely, creating a direct dependency on OpenAI SDK. This makes it harder to:
- Mock in tests
- Switch providers
- Maintain consistent error handling

#### Module-Level Settings Access

```python
# handlers.py:24
settings = get_settings()
setup_logging(level=settings.log_level)
```

Settings are accessed at module load time, which can cause issues in testing and makes the dependency implicit.

---

## Proposed Improvements

### Priority 1: Extract HITL Utilities ✅ COMPLETED

**Effort: Low | Impact: High**

Created `app/utils/hitl.py`:

```python
"""HITL (Human-in-the-Loop) utilities shared across nodes."""

def parse_hitl_message(content: str) -> tuple[str, str] | None:
    """Parse [HITL:checkpoint:choice] message format."""
    ...

def parse_hitl_choice(content: str) -> str | None:
    """Extract just the choice from a HITL message."""
    ...

def clear_hitl_flags() -> dict:
    """Return dict of cleared HITL flags for state updates."""
    ...

def is_hitl_message(content: str) -> bool:
    """Check if content is a HITL synthetic message."""
    ...
```

Imports updated in:
- `agents/intake.py` ✅
- `agents/research.py` ✅
- `agents/advise.py` ✅

---

### Priority 2: Split research.py ✅ COMPLETED

**Effort: High | Impact: High**

Created flat file structure (simpler than subdirectory):

```
agents/
├── research.py           # 469 lines - node orchestration (was 1427)
├── research_explorer.py  # 611 lines - explorer_step(), query generation
├── research_enricher.py  # 203 lines - enricher_step(), enrich_living_table()
└── research_table.py     # 129 lines - table utilities
```

**Result:**
- `research.py` reduced from 1427 → 469 lines (67% reduction)
- Clear separation of concerns
- Each module has single responsibility

---

### Priority 3: Split handlers.py ✅ COMPLETED

**Effort: Medium | Impact: Medium**

Created focused modules:

```
chat/
├── __init__.py
├── handlers.py          # 292 lines - on_message, on_chat_start, on_chat_end
├── table_rendering.py   # 228 lines - send_product_table, send_table_with_export, render_table_markdown
├── hitl_actions.py      # 174 lines - on_hitl_action, render_action_buttons
├── citations.py         # 32 lines - format_response_with_citations
└── starters.py          # 25 lines - set_starters, STARTER_DIRECT_RESPONSES
```

**Result:**
- `handlers.py` reduced from 723 → 292 lines (60% reduction)
- Clear separation of concerns
- Each module has single responsibility

---

### Priority 4: Standardize Service Instantiation

**Effort: Medium | Impact: Medium**

Choose one pattern and apply consistently:

**Option A: `@lru_cache` for all singletons**

```python
@lru_cache
def get_lattice_service() -> LatticeService:
    return LatticeService()

@lru_cache
def get_search_strategy_service() -> SearchStrategyService:
    return SearchStrategyService()
```

**Option B: Dependency injection container**

```python
# services/container.py
class ServiceContainer:
    _llm_service: LLMService | None = None
    _lattice_service: LatticeService | None = None

    @classmethod
    def get_llm_service(cls) -> LLMService:
        if cls._llm_service is None:
            cls._llm_service = LLMService(get_settings())
        return cls._llm_service
```

---

### Priority 5: Remove Deprecated comparison_table ✅ COMPLETED

**Effort: Medium | Impact: Low**

Removed all deprecated code:

1. ✅ Audited all usages of `comparison_table`
2. ✅ Verified `living_table` provides equivalent functionality
3. ✅ Updated `advise.py` to use only `living_table`
4. ✅ Removed fallback to `comparison_table` in `research.py`
5. ✅ Removed field from `state.py`
6. ✅ Removed `enricher_step()` and `meets_requirements()` from `research_enricher.py`
7. ✅ Removed `build_field_definitions_list()` from `research_table.py`
8. ✅ Removed vestigial `phase` field from `state.py`

---

### Priority 6: Add Error Handling Improvements

**Effort: Medium | Impact: Medium**

#### Add Retry Logic

```python
# utils/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True,
)
async def with_retry(func, *args, **kwargs):
    return await func(*args, **kwargs)
```

#### Replace Bare Exceptions

```python
# Before
except Exception:
    pass

# After
except (KeyError, ValueError) as e:
    logger.warning(f"Failed to get product name: {e}")
```

---

## Files Changed Summary

### Completed Changes

| Change Type | Files |
|-------------|-------|
| New files | `utils/hitl.py`, `agents/research_explorer.py`, `agents/research_enricher.py`, `agents/research_table.py` |
| New files | `chat/hitl_actions.py`, `chat/table_rendering.py`, `chat/citations.py`, `chat/starters.py` |
| Modified | `agents/intake.py`, `agents/advise.py`, `agents/research.py`, `chat/handlers.py` |
| Modified | `models/state.py` (removed deprecated `comparison_table` and vestigial `phase` field) |
| Modified | `agents/research_enricher.py` (removed deprecated `enricher_step()` and `meets_requirements()`) |
| Modified | `agents/research_table.py` (removed unused `build_field_definitions_list()`) |
| Modified | `tests/models/test_state.py` (updated test to check `current_phase` instead of `phase`) |

---

## Verification Checklist

Before implementing changes:

- [ ] All tests pass (`make test`)
- [ ] Lint passes (`make check`)
- [ ] Manual testing of all three phases
- [ ] HITL buttons work correctly
- [ ] ProductTable renders correctly
- [ ] CSV export works
- [ ] Thread naming updates correctly
