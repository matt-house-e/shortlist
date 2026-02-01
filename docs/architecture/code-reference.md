# Code Reference

Detailed class and function reference for the Shortlist codebase.

## app/agents/

### workflow.py (311 lines)

Graph definition and orchestration.

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `WorkflowResult` | 167 | Result from processing a message through the workflow |

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `parse_hitl_message(content)` | 17 | Parse HITL synthetic message into (checkpoint, choice) tuple |
| `router_node(state)` | 40 | Route incoming messages to correct phase node based on current_phase |
| `create_workflow(llm_service)` | 101 | Create and compile the LangGraph workflow with 3-phase structure |
| `process_message(workflow, message, user_id, session_id)` | 199 | Process user message through workflow (returns content string) |
| `process_message_with_state(workflow, message, user_id, session_id)` | 221 | Process user message and return full WorkflowResult |

---

### intake.py (308 lines)

INTAKE node - Gather requirements through conversation.

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `UserRequirements` | 27 | Pydantic model for structured user requirements extraction |
| `IntakeDecision` | 58 | Decision about how to continue the intake conversation |

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `format_requirements_summary(requirements)` | 78 | Format requirements dict into human-readable HITL confirmation text |
| `intake_node(state)` | 126 | Main INTAKE node - multi-turn conversation for requirement gathering |

---

### research.py (420 lines)

RESEARCH node - Orchestrate candidate discovery and enrichment.

**Execution Paths:**

1. **New Search** (`need_new_search=True`): Run explorer, add rows, enrich all
2. **Add Fields** (`requested_fields` set, `need_new_search=False`): Add new fields, enrich only new columns
3. **Re-enrich** (`need_new_search=False`, no `requested_fields`): Re-enrich flagged cells

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `_format_field_name(name)` | 21 | Convert field_name_like_this to "Field Name Like This" |
| `_format_fields_for_display(field_definitions)` | 26 | Format field definitions for HITL confirmation display |
| `research_node(state)` | 77 | Main RESEARCH node - orchestrates 3 execution paths |

---

### research_explorer.py (621 lines)

Explorer sub-step - Find product candidates via web search.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `summarize_requirements(requirements)` | 48 | Create concise requirements summary for qualification prompts |
| `generate_search_queries(llm_service, requirements)` | 95 | Generate 10-15 diverse search queries using SearchStrategyService |
| `match_citation_to_product(product_name, manufacturer, citations)` | 171 | Find best matching citation URL for a product |
| `extract_candidates_from_response(response_content, citations)` | 234 | Extract product candidates from web search response |
| `normalize_name(name)` | 301 | Normalize product name for deduplication |
| `deduplicate_candidates(candidates)` | 306 | Deduplicate candidates by fuzzy name matching |
| `_execute_web_search(llm_service, query)` | 349 | Execute single web search with retry logic (decorator) |
| `execute_parallel_searches(queries, llm_service, product_type)` | 361 | Execute multiple web searches in parallel |
| `generate_field_definitions(product_type, requirements, llm_service)` | 431 | Generate field definitions (standard + category-specific + qualification) |
| `explorer_step(state)` | 528 | Main explorer entry point - returns (candidates, field_definitions) |

---

### research_enricher.py (117 lines)

Enricher sub-step - Enrich living table via Lattice.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `enrich_living_table(table)` | 10 | Enrich PENDING cells in the living table via Lattice service |

---

### research_table.py (106 lines)

Living table management utilities.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `get_or_create_living_table(state)` | 10 | Get existing living table from state or create new one |
| `add_candidates_to_table(table, candidates)` | 26 | Add candidates to table with deduplication, returns (added, duplicates) |
| `add_requested_fields_to_table(table, requested_fields)` | 68 | Add user-requested fields, marks rows PENDING for new fields |

---

### advise.py (440 lines)

ADVISE node - Present recommendations and handle refinement.

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `UserIntent` | 56 | Detected user intent (satisfied, more_options, new_fields, change_requirements, question) |

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `_get_intent_description(intent_type, extracted_fields)` | 69 | Get human-readable description of detected intent |
| `_execute_confirmed_intent(state, pending_intent, pending_details)` | 88 | Execute a confirmed intent action (routes to appropriate node) |
| `advise_node(state)` | 166 | Main ADVISE node - present results, detect intent, handle refinement |

---

## app/chat/

### handlers.py (292 lines)

Main Chainlit event handlers.

**Constants:**

| Constant | Line | Description |
|----------|------|-------------|
| `PHASE_TO_AGENT_NAME` | 34 | Map phase names to display names |
| `PHASE_TRANSITION_TOASTS` | 41 | Toast notification config for phase transitions |

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `get_agent_name(phase)` | 61 | Get display name for agent based on current phase |
| `emit_phase_transition_toast(previous_phase, current_phase)` | 66 | Emit toast notification on phase change |
| `update_thread_name_from_product(product_type)` | 84 | Update chat thread name to product being researched |

**Chainlit Decorators:**

| Decorator | Line | Description |
|-----------|------|-------------|
| `@cl.data_layer` | 122 | Create Chainlit data layer (optional, requires PostgreSQL) |
| `@cl.password_auth_callback` | 139 | Handle password authentication |
| `@cl.on_chat_start` | 150 | Initialize new chat session |
| `@cl.on_message` | 175 | Handle incoming user messages |
| `@cl.on_chat_end` | 266 | Clean up when chat session ends |
| `@cl.on_settings_update` | 277 | Handle user settings updates |

---

### citations.py (32 lines)

Citation formatting utilities.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `format_response_with_citations(content, citations)` | 4 | Append Sources section with clickable citation links |

---

### hitl_actions.py (174 lines)

HITL (Human-in-the-Loop) action handling.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `render_action_buttons(result, message_content, agent_name)` | 13 | Render action buttons based on WorkflowResult HITL state |
| `remove_current_actions()` | 57 | Remove any currently displayed action buttons |

**Chainlit Decorators:**

| Decorator | Line | Description |
|-----------|------|-------------|
| `@cl.action_callback("hitl_action")` | 65 | Handle all HITL button clicks |

---

### starters.py (25 lines)

Welcome screen prompts.

**Constants:**

| Constant | Line | Description |
|----------|------|-------------|
| `STARTER_DIRECT_RESPONSES` | 6 | Direct responses for starter prompts (skips LLM) |

**Chainlit Decorators:**

| Decorator | Line | Description |
|-----------|------|-------------|
| `@cl.set_starters` | 14 | Define starter prompts for welcome screen |

---

### table_rendering.py (228 lines)

Table display and CSV export.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `render_table_markdown(living_table_data, max_rows)` | 15 | Render living table as markdown string |
| `send_table_with_export(living_table_data, agent_name, include_export_button)` | 40 | Send comparison table with optional export button |
| `send_product_table(living_table_data, user_requirements, llm_service, agent_name, include_export_button)` | 79 | Send table as custom React ProductTable element |

**Chainlit Decorators:**

| Decorator | Line | Description |
|-----------|------|-------------|
| `@cl.action_callback("export_csv")` | 165 | Handle CSV export button click |

---

## app/models/

### state.py (194 lines)

Central state schema for LangGraph workflow.

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `AgentState` | 11 | TypedDict for fat state pattern - all workflow data in single object |

**AgentState Sections:**

- **Message History** (line 35): `messages` with `add_messages` reducer
- **Workflow Control** (line 42): `current_node`, `current_phase`
- **User Context** (line 47): `user_id`, `session_id`, `user_metadata`
- **Turn Metrics** (line 58): Token counts, timing, workflow tracking
- **Web Search** (line 78): Citations, sources, OpenAI response ID
- **Domain-Specific** (line 89): Requirements, candidates, living_table, refinement
- **HITL Control** (line 117): Confirmation flags, action choices, pending data

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `create_initial_state(user_id, session_id, ...)` | 139 | Create initial state for new conversation |

---

### schemas/base.py (52 lines)

Base schema utilities.

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `BaseSchema` | 8 | Base Pydantic model with common configuration |
| `TimestampedSchema` | 28 | Base schema with created_at/updated_at fields |

---

### schemas/shortlist.py (513 lines)

Domain-specific Pydantic schemas.

**Enums:**

| Enum | Line | Description |
|------|------|-------------|
| `WorkflowPhase` | 15 | Workflow phases: INTAKE, RESEARCH, ADVISE |
| `CellStatus` | 28 | Cell status: PENDING, ENRICHED, FAILED, FLAGGED |
| `FieldCategory` | 96 | Field categories: STANDARD, CATEGORY, USER_DRIVEN, QUALIFICATION |
| `DataType` | 105 | Data types: STRING, NUMBER, BOOLEAN, LIST, DICT |
| `RefinementTrigger` | 430 | Refinement triggers |
| `SearchAngle` | 447 | Search angle types for diverse queries |

**Classes:**

| Class | Line | Description |
|-------|------|-------------|
| `TableCell` | 37 | Single cell with value, status, metadata |
| `TableRow` | 47 | Row representing a product candidate |
| `UserRequirements` | 58 | User requirements for product search |
| `Candidate` | 86 | Product candidate model |
| `FieldDefinition` | 115 | Definition for comparison table field |
| `ComparisonTable` | 126 | Living comparison table with cell-level tracking |
| `RefinementEntry` | 439 | Entry tracking refinement loop iteration |
| `SearchQuery` | 469 | Single search query with strategic angle |
| `SearchQueryPlan` | 483 | Plan for multiple diverse search queries |
| `DiscoveredCandidate` | 503 | Product candidate discovered via web search |

**ComparisonTable Methods:**

| Method | Line | Description |
|--------|------|-------------|
| `has_candidate(name)` | 158 | Check if candidate with similar name exists |
| `add_row(candidate, source_query)` | 178 | Add row with deduplication |
| `add_field(field)` | 212 | Add field, mark existing rows PENDING |
| `update_cell(row_id, field_name, value, status, ...)` | 232 | Update cell value and status |
| `get_pending_cells()` | 273 | Get cells needing enrichment |
| `get_field_names(exclude_internal)` | 287 | Get list of field names |
| `to_markdown(max_rows, show_pending, exclude_internal)` | 304 | Render as markdown table |
| `to_csv(exclude_internal)` | 372 | Export to CSV format |
| `get_qualified_rows()` | 405 | Get rows meeting requirements |
| `get_row_count()` | 409 | Get total row count |
| `get_enrichment_progress()` | 413 | Get (enriched_cells, total_cells) |

---

## app/utils/

### hitl.py (45 lines)

HITL utilities shared across agent nodes.

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `parse_hitl_choice(content)` | 8 | Extract choice from HITL synthetic message |
| `clear_hitl_flags()` | 29 | Return dict of cleared HITL state flags |
| `is_hitl_message(content)` | 43 | Check if content is a HITL synthetic message |

---

### retry.py (40 lines)

Retry utilities for external service calls.

**Decorators:**

| Decorator | Line | Description |
|-----------|------|-------------|
| `openai_retry` | 17 | Retry on transient + rate limit errors (3 attempts, exponential backoff) |
| `web_search_retry` | 34 | More lenient retry for web search (2 attempts, fail fast) |

---

## app/auth/

### oauth.py (82 lines)

OAuth/SSO authentication provider (placeholder).

**Functions:**

| Function | Line | Description |
|----------|------|-------------|
| `oauth_callback(provider_id, token, raw_user_data, default_user)` | 10 | Handle OAuth authentication callback |
| `fetch_azure_user_details(access_token)` | 64 | Fetch user details from Microsoft Graph API |
