# Shortlist - AI Architecture Spec

> A living design document for the agent workflow, tools, and services layer.

---

## 1. Overview

**Shortlist** is a multi-phase AI system for researching and comparing purchase options.

### Problem

Manual product research is tedious. Users spend hours across review sites, retailer pages, and forums trying to answer: "What should I buy?" They want a curated, comparable shortlist—not a wall of search results.

### Core Principle

> **Progressive Refinement**: Users narrow down through conversation, not upfront filters. The system learns what matters as the dialogue unfolds, and users can always say "more like this" or "but cheaper."

### What Shortlist Does

```
┌─────────┐     ┌──────────┐     ┌────────┐
│ INTAKE  │────▶│ RESEARCH │────▶│ ADVISE │───▶ END
└─────────┘     └──────────┘     └────┬───┘
     ▲                                │
     └────────────────────────────────┘
                 (refinement)
```

1. **INTAKE** - Gathers requirements through multi-turn conversation
2. **RESEARCH** - Finds candidates online and builds a comparison table
3. **ADVISE** - Presents top recommendations and handles refinement
4. **Refinement loop** - User can adjust criteria, request more options, or add comparison dimensions

### Example Interaction

> **User:** I want a kettle with variable temperature, under £50
>
> **System:** What's most important—speed, capacity, or build quality?
>
> **User:** Build quality, prefer stainless steel
>
> **System:** *(shows Confirm Requirements / Edit buttons)*
>
> **User:** *(clicks Confirm Requirements)*
>
> **System:** Researching... Found 24 options. Here's your shortlist:
>
> | Product | Price | Material | Temp Control |
> |---------|-------|----------|--------------|
> | Fellow Stagg | £45 | Steel | 5 presets |
> | Bonavita | £38 | Steel | Variable |
>
> The Fellow Stagg wins on build quality. Bonavita is best value.
>
> **User:** Find me 5 more like the Fellow but under £40
>
> **System:** *(loops back to RESEARCH with updated criteria)*

### Key Design Decision: Specs vs Listings

Shortlist distinguishes between two types of URLs:

| Type | Purpose | Example |
|------|---------|---------|
| **Official product page** | Canonical source for specifications | BMW's page for the M4 Competition |
| **Purchase listings** | Actual places to buy | AutoTrader listing, Amazon product page |

This separation ensures users get authoritative specs alongside real purchase options.

### Why Multiple Phases?

A single monolithic agent would be harder to debug and reason about. Separating into distinct phases provides:

- **Focused responsibility** - Each phase does one thing well
- **Isolated failures** - Problems are traceable to specific phases
- **Clean refinement** - Easy to loop back to the right phase based on what changed
- **Predictable flow** - Users always experience INTAKE → RESEARCH → ADVISE

### Output Artifact

The primary output is a **curated comparison table** containing:

- Product name and official URL (manufacturer specs)
- Comparison dimensions relevant to user requirements
- Purchase links (actual listings)
- Trade-off analysis highlighting top recommendations

Users can view the top 5 recommendations or export the full comparison as CSV.

### Scope Boundaries

| In Scope | Out of Scope |
|----------|--------------|
| Any product category (generalised) | Vertical-specific optimisations |
| Single-session conversations | Persistent user accounts |
| Web-scraped product data | Retailer API integrations |
| Comparison and recommendation | Checkout or payment |

### What This Spec Covers

This document defines the **AI layer behavior** for Shortlist. The existing template handles UI, auth, database, and deployment.

**Spec scope:**
- Phase definitions and responsibilities
- State schema (data flowing between phases)
- Tool interfaces (inputs, outputs, constraints)
- User interaction patterns
- Guardrails and error handling

---

## 2. Architecture Pattern

### Three-Phase State-Driven Workflow

Shortlist uses a **state-driven workflow** with three phases. All phases share a single state object, and transitions are determined by conditions on that state.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│    User message                                                 │
│         │                                                       │
│         ▼                                                       │
│    ┌──────────┐                                                 │
│    │  ROUTER  │ (checks current_phase)                         │
│    └────┬─────┘                                                 │
│         │                                                       │
│    ┌────┴────────────────────────┐                              │
│    │                             │                              │
│    ▼                             ▼                              │
│    ┌──────────┐            ┌──────────┐                         │
│    │  INTAKE  │            │  ADVISE  │ ◄───────────────────┐   │
│    └────┬─────┘            └────┬─────┘                     │   │
│         │ requirements          │                           │   │
│         │ ready                 │ user intent               │   │
│         ▼                       ▼                           │   │
│    ┌──────────┐           ┌────┴────┬───────────┐           │   │
│    │ RESEARCH │           │         │           │           │   │
│    │          │           ▼         ▼           ▼           │   │
│    │ Explorer │         END    new fields   more options    │   │
│    │    │     │                     │           │           │   │
│    │    ▼     │                     └─────┬─────┘           │   │
│    │ Enricher │                           │                 │   │
│    └────┬─────┘                           ▼                 │   │
│         │                           ┌──────────┐            │   │
│         │ table ready               │ RESEARCH │────────────┘   │
│         └──────────────────────────▶└──────────┘                │
│                                                                 │
│    (change_requirements loops back via ROUTER → INTAKE)         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### The Router Pattern

The **router node** is the entry point for all incoming user messages. It checks `current_phase` and directs the message to the appropriate node:

| current_phase | Routes to | Rationale |
|---------------|-----------|-----------|
| `intake` (or unset) | INTAKE | Gathering requirements |
| `advise` | ADVISE | User responding to recommendations |
| `research` | ADVISE | Edge case: user shouldn't message during research |

This pattern enables proper human-in-the-loop behavior where both INTAKE and ADVISE can receive and process user messages independently, rather than all messages flowing through INTAKE first.

### Phase Summary

| Phase | Nature | Purpose | Tools |
|-------|--------|---------|-------|
| **INTAKE** | Conversational | Gather requirements through dialogue | None |
| **RESEARCH** | Automated | Find candidates and build comparison table | Web search, Lattice |
| **ADVISE** | Conversational | Present results and handle refinement | Purchase links, CSV export |

---

### Design Decision: State-Driven vs Autonomous Agents

We evaluated two architectural approaches:

| Autonomous Agents | State-Driven Workflow |
|-------------------|----------------------|
| Agents decide when to hand off | State conditions trigger transitions |
| Agents have independent memory | Single shared state |
| Unpredictable conversation paths | "On rails" — predictable |
| Complex failure modes | Failures isolated to phases |

**We chose state-driven because:**

1. **Matches user mental model**
   - "I tell you what I want" → INTAKE
   - "You go find stuff" → RESEARCH
   - "You show me and help me decide" → ADVISE

2. **Refinement is natural**
   - ADVISE determines where to loop back based on what changed
   - No complex negotiation between autonomous agents

3. **Predictable and debuggable**
   - Always flows INTAKE → RESEARCH → ADVISE
   - Loops back based on explicit user intent
   - State is inspectable at any point

---

### Design Decision: Three Phases (Not Four or Two)

**Why not separate Explorer and Enricher into their own phases?**
- They always run in sequence
- The only variation is whether Explorer runs (new search needed) or is skipped (re-enrich existing candidates)
- A single flag in state controls this
- Fewer phases = simpler to reason about

**Why not combine INTAKE and ADVISE?**
- Different prompts and personas
- Different tools available
- Different exit conditions
- Easier to debug when separated

---

### Phase Transitions

#### INTAKE → RESEARCH

| Condition | Transition |
|-----------|------------|
| Requirements complete (product type, budget, priorities defined) | → RESEARCH |
| Requirements incomplete | → Stay in INTAKE (continue dialogue) |

#### RESEARCH → ADVISE

| Condition | Transition |
|-----------|------------|
| Comparison table ready | → ADVISE |
| Research failed | → ADVISE (with error context) |

#### ADVISE → Next Phase

| User Intent | Transition | State Update |
|-------------|------------|--------------|
| "I'm done" / selects product | → END | — |
| "Add energy efficiency to comparison" | → RESEARCH | New fields to enrich |
| "Find me 10 more like these" | → RESEARCH | Need new search = true |
| "Actually, budget is now £30" | → INTAKE | Requirements changed |
| Asks follow-up question | → Stay in ADVISE | — |

---

### RESEARCH Phase: Three Data Flow Paths

RESEARCH operates on the Living Table and supports three distinct data flow paths:

```
RESEARCH
│
├── PATH 1: New Search (need_new_search = true)
│   │
│   ├── EXPLORER
│   │   ├── Input: Requirements from state
│   │   ├── Action: Web search (10-15 diverse queries)
│   │   ├── Output: Candidates added to Living Table
│   │   └── Also determines: Field definitions
│   │
│   └── ENRICHER
│       ├── Input: Living Table with PENDING cells
│       ├── Action: Bulk enrichment via Lattice
│       └── Output: Cells updated to ENRICHED/FAILED
│
├── PATH 2: Add Fields Only (requested_fields not empty)
│   │
│   ├── Add field definitions to Living Table
│   │   (marks all existing rows PENDING for new field)
│   │
│   └── ENRICHER
│       └── Only enriches cells for new field (incremental)
│
└── PATH 3: Re-enrich (flagged/pending cells exist)
    │
    └── ENRICHER
        └── Only enriches PENDING or FLAGGED cells
```

**When Explorer is skipped:**
- User requested new comparison fields only (Path 2)
- Re-enriching flagged cells after user correction (Path 3)

**Benefits of incremental enrichment:**
- Adding a new field doesn't re-enrich existing data
- Failed cells can be retried individually
- Users can flag incorrect data for re-enrichment

---

### Tool Boundaries

Tools are restricted by phase to enforce separation of concerns:

| Phase | Available Tools | Rationale |
|-------|-----------------|-----------|
| INTAKE | None | Focus on understanding, not doing |
| RESEARCH | Web search, Lattice enrichment | Power tools for data gathering |
| ADVISE | Purchase link lookup, CSV export | Fulfill final requests without re-entering pipeline |

---

### Shared State Pattern

All phases read from and write to a single shared state. There is no isolated memory per phase.

**Benefits:**
- Full conversation history visible to all phases
- Requirements, candidates, and comparison data always accessible
- State is inspectable at any point for debugging
- Refinement accumulates context naturally across loops

**Key state fields** (defined in Section 4):
- User requirements
- Candidate list
- Field definitions
- Comparison table
- Refinement history

---

### Human-in-the-Loop Behavior

| Phase | User Interaction |
|-------|------------------|
| INTAKE | Waits for user input each turn |
| INTAKE → RESEARCH | Requires button confirmation (Confirm Requirements / Edit) |
| RESEARCH (Explorer → Enricher) | Requires button confirmation (Enrich Now / Modify Fields) |
| ADVISE | Waits for user input each turn |

The system presents results and waits for user direction. It does not proceed to expensive operations (search, enrichment) without explicit user confirmation via action buttons.

**HITL Checkpoints:**
1. **Requirements confirmation** — After INTAKE determines requirements are sufficient, shows "Confirm Requirements" / "Edit Requirements" buttons
2. **Field confirmation** — After Explorer finds candidates, shows "Enrich Now" / "Modify Fields" buttons before Lattice enrichment
3. **Refinement confirmation** — In ADVISE, may show confirmation for expensive refinement operations

**Implementation:** The router pattern ensures messages reach the correct phase. When a user sends a message:
1. Router checks `current_phase`
2. Message is directed to INTAKE or ADVISE accordingly
3. The receiving node processes the message and may transition phases
4. Control returns to user (via `__end__`) when waiting for input

---

## 3. Agent Definitions

This section defines each agent's behavior, inputs, outputs, and constraints.

---

### INTAKE Agent

**Purpose:** Gather user requirements through multi-turn conversation.

#### Inputs

| Field | Source | Description |
|-------|--------|-------------|
| User message | Chainlit | Current user input |
| Conversation history | State | Previous messages in session |
| Partial requirements | State | Any requirements already captured |

#### Outputs

| Field | Description |
|-------|-------------|
| Requirements object | Structured data: product type, budget, priorities, constraints |
| Transition signal | Whether requirements are complete |

#### Behavior

INTAKE engages in multi-turn dialogue to understand what the user wants to buy:

1. Acknowledge the user's initial request
2. Ask clarifying questions to fill gaps in requirements
3. Confirm understanding before proceeding
4. Update state with structured requirements

**Minimum requirements before exit:**
- Product type or category identified
- At least one constraint (budget, feature, or preference)
- User has confirmed readiness to search

#### Persona & Tone

- Helpful shopping assistant, not an interrogator
- Ask focused, specific questions (not "tell me everything")
- Offer sensible defaults when user is uncertain
- Keep it conversational, not form-filling
- Maximum 2-3 questions per turn

**Example good behavior:**
> "Under £50, got it. What matters most—build quality, speed, or ease of cleaning?"

**Example bad behavior:**
> "Please provide: 1) Budget range 2) Preferred materials 3) Capacity requirements 4) Temperature settings 5) Brand preferences..."

#### Exit Conditions

| Condition | Result |
|-----------|--------|
| Requirements sufficient to search | → Transition to RESEARCH |
| Requirements incomplete | → Stay in INTAKE, ask another question |
| User explicitly asks to search now | → Transition to RESEARCH with current requirements |

#### Acceptance Criteria

- [ ] Can summarize requirements in one sentence
- [ ] Requirements contain product type and at least one constraint
- [ ] User has had opportunity to clarify priorities
- [ ] No interrogation-style question dumps

#### Error Handling

| Scenario | Response |
|----------|----------|
| User is vague ("something good") | Ask for one specific constraint: budget OR key feature |
| User wants to skip questions | Proceed with stated requirements, note gaps |
| User changes topic entirely | Gently redirect or confirm they want to start over |
| User asks unrelated question | Answer briefly, then return to requirements |

---

### RESEARCH Agent

**Purpose:** Find product candidates and build a structured comparison table.

#### Inputs

| Field | Source | Description |
|-------|--------|-------------|
| Requirements | State | Product type, budget, priorities, constraints |
| Existing candidates | State | Previously found candidates (if re-enriching) |
| Field definitions | State | Comparison fields (if already defined) |
| New fields requested | State | Additional fields to add (from refinement) |
| Need new search flag | State | Whether to run Explorer or skip to Enricher |

#### Outputs

| Field | Description |
|-------|-------------|
| Candidates | List of products with name, official URL, basic info |
| Field definitions | Comparison dimensions appropriate to product category |
| Comparison table | Enriched data for all candidates across all fields |

#### Behavior

RESEARCH runs automatically without user interaction. It contains two sub-steps:

1. **Explorer** (conditional) — Find candidates via web search
2. **Enricher** (always) — Build comparison table via Lattice

```
IF need_new_search = true:
    Run Explorer → produces candidates + field definitions

ALWAYS:
    Run Enricher → produces comparison table
```

#### Exit Conditions

| Condition | Result |
|-----------|--------|
| Comparison table ready | → Transition to ADVISE |
| Research failed completely | → Transition to ADVISE with error context |

#### Acceptance Criteria

- [ ] At least 20 candidates found (or all available if fewer exist)
- [ ] All candidates have official product URL
- [ ] Field definitions appropriate to product category
- [ ] Comparison table has no empty required fields
- [ ] Data types are consistent across candidates

---

### RESEARCH > Explorer (Sub-step)

**Purpose:** Find product candidates via web search.

#### Inputs

| Field | Source | Description |
|-------|--------|-------------|
| Requirements | State | What the user is looking for |

#### Outputs

| Field | Description |
|-------|-------------|
| Candidates | List of 20+ products (name, official URL, basic info) |
| Field definitions | Proposed comparison dimensions for this product category |

#### Behavior

1. Generate 10-15 diverse search queries using multi-angle strategy
2. Execute web searches in parallel
3. Parse and filter results for relevance
4. Extract official product URLs using reasoning model (o4-mini)
5. Determine appropriate comparison fields based on product category
6. Add candidates to Living Table (with deduplication)
7. Target 30 candidates (configurable via max_products setting)

**Diverse Search Strategy:**

| Angle | Example Query |
|-------|---------------|
| REVIEW_SITE | "best electric kettles site:which.co.uk" |
| REDDIT | "electric kettle recommendation site:reddit.com" |
| BRAND_CATALOG | "Fellow kettles official" |
| COMPARISON | "Fellow Stagg vs Bonavita comparison" |
| BUDGET | "best electric kettle under £50" |
| FEATURE_FOCUS | "variable temperature kettle" |
| USE_CASE | "kettle for pour over coffee" |
| ALTERNATIVES | "Fellow Stagg alternatives" |

**Agentic Web Search:**
- Uses OpenAI o4-mini reasoning model for multi-step search
- Model can perform multiple searches and visit URLs to verify sources
- Filters out retailer and review sites; prioritizes official manufacturer pages

**Field definition logic:**
- Standard fields for all categories: name, price, official_url
- Category-specific fields based on product type (e.g., capacity, wattage, material for kettles)
- User-driven fields based on stated priorities (e.g., "temperature_control" if user mentioned it)
- Only verifiable, objective specs allowed (no subjective ratings, no cost estimates)

#### Acceptance Criteria

- [ ] Candidates match user requirements
- [ ] Official product URLs (not retailer listings)
- [ ] No duplicate products (Living Table deduplication)
- [ ] Field definitions cover user's stated priorities
- [ ] Field definitions are verifiable specs (no subjective ratings)
- [ ] Target 30 candidates (configurable)

#### Error Handling

| Scenario | Response |
|----------|----------|
| No results found | Broaden search criteria, report to ADVISE if still empty |
| Too few results (<10) | Note limited availability, proceed with what's found |
| Too many results (>100) | Apply stricter relevance filtering |
| Ambiguous product category | Make best guess, note assumption for ADVISE |

---

### RESEARCH > Enricher (Sub-step)

**Purpose:** Build structured comparison table using Lattice bulk enrichment.

#### Inputs

| Field | Source | Description |
|-------|--------|-------------|
| Candidates | Explorer or State | Products to enrich |
| Field definitions | Explorer or State | What dimensions to compare |

#### Outputs

| Field | Description |
|-------|-------------|
| Comparison table | Structured data: all candidates × all fields |
| Enrichment metadata | Success/failure status per candidate |

#### Behavior

1. Get PENDING cells from Living Table via `get_pending_cells()`
2. Prepare field definitions for Lattice (from Living Table fields)
3. Call Lattice bulk enrichment for pending cells only
4. Update each cell in Living Table via `update_cell()`
5. Handle partial failures at cell level (mark individual cells FAILED)

**Lattice integration:**
- Uses web-enriched chain for real-time data (prices, availability)
- Field definitions follow Lattice CSV schema (Category, Field, Prompt, Data_Type)
- Async processing for performance
- Supports incremental enrichment (only processes PENDING/FLAGGED cells)

#### Acceptance Criteria

- [ ] All PENDING cells processed (success or marked FAILED)
- [ ] Required fields populated for successful cells
- [ ] Data types match field definitions
- [ ] Cell-level status tracking (ENRICHED/FAILED per cell)
- [ ] At least 80% of cells successfully enriched

#### Error Handling

| Scenario | Response |
|----------|----------|
| Lattice fails for single cell | Mark cell as FAILED with error message, continue others |
| Lattice fails entirely | Retry once; if still failing, report error to ADVISE |
| Field returns empty for all rows | Flag field as problematic, report to user |
| Timeout on large batch | Process in smaller batches, merge results |
| User flags incorrect data | Mark cell as FLAGGED, re-enrich on next pass |

---

### ADVISE Agent

**Purpose:** Present comparison results, make recommendations, and handle refinement requests.

#### Inputs

| Field | Source | Description |
|-------|--------|-------------|
| Comparison table | State | Enriched product data |
| Requirements | State | User's original requirements and priorities |
| Conversation history | State | Full dialogue context |
| Enrichment metadata | State | Which candidates succeeded/failed |

#### Outputs

| Field | Description |
|-------|-------------|
| Recommendations | Top 5 products with reasoning |
| User intent | Detected next action (done, refine, more options, etc.) |
| Refinement details | What changed if user requests refinement |

#### Behavior

ADVISE operates in two modes:

**Mode 1: Present Results (first entry from RESEARCH)**
1. Analyze comparison table against user requirements
2. Rank candidates based on user priorities
3. Present top 5 with trade-off explanations
4. Return control to user and wait for response

**Mode 2: Handle Response (user sent a new message)**
1. Interpret user intent from their message
2. Generate conversational response
3. Route to appropriate phase based on intent

**Presentation format:**
- Show top 5 in table format
- Highlight why each made the list
- Call out trade-offs between top options
- Offer to show full comparison or export CSV

#### Persona & Tone

- Knowledgeable advisor, not salesperson
- Explain trade-offs clearly and honestly
- Don't push a single option; present choices
- Acknowledge limitations in data
- Be concise; user can ask for details

**Example good behavior:**
> "The Fellow Stagg scores highest on build quality, but at £45 it's near your budget limit. The Bonavita is £38 with similar features—the trade-off is slightly lower build quality ratings. Which matters more to you?"

**Example bad behavior:**
> "Based on my analysis, the Fellow Stagg is definitely the best option and you should buy it immediately."

#### Exit Conditions

| User Intent | Result |
|-------------|--------|
| Satisfied / selects product | → END |
| Requests purchase links | → Stay in ADVISE, call purchase link tool |
| Requests CSV export | → Stay in ADVISE, call export tool |
| Asks follow-up question | → Stay in ADVISE, answer question |
| Wants new comparison fields | → RESEARCH (Enricher only) |
| Wants more candidates | → RESEARCH (Explorer + Enricher) |
| Changes requirements | → INTAKE |

#### Acceptance Criteria

- [ ] Top 5 clearly presented with reasoning
- [ ] Trade-offs explained, not hidden
- [ ] User can make informed decision
- [ ] Refinement requests correctly interpreted
- [ ] Routing to correct phase based on intent

#### Error Handling

| Scenario | Response |
|----------|----------|
| Comparison table is empty | Explain no results found, offer to adjust requirements |
| All candidates failed enrichment | Report data issue, offer to try different search |
| User request is ambiguous | Ask clarifying question before routing |
| User frustrated with results | Acknowledge, offer concrete next steps |

---

## 4. State Schema

The workflow uses a single shared state object (fat state pattern). All agents read from and write to this state. This section describes the **intent** of what we need to capture—exact field names and structures will emerge during implementation.

---

### Core Principle

> State should capture everything needed for any agent to do its job without re-asking the user or re-computing previous work.

---

### What We Need to Capture

#### 1. User Requirements

The structured understanding of what the user wants to buy.

| Concept | Intent | Example |
|---------|--------|---------|
| Product type | What category of thing | "electric kettle", "used car", "hotel in Paris" |
| Budget | Price constraints | Max £50, or range £30-50 |
| Must-haves | Non-negotiable features | "variable temperature", "diesel engine" |
| Nice-to-haves | Preferred but flexible | "stainless steel", "parking included" |
| Priorities | What to optimize for | "build quality over price", "fuel efficiency" |
| Specifications | Positive filters that narrow search | "second hand", "year 2010-2020", "UK only", "manual transmission" |
| Constraints | Things to explicitly avoid (negatives only) | "no plastic", "not from X brand", "avoid high mileage" |

**Note on Specifications vs Constraints:**
- **Specifications** are positive narrowing filters (what to include)
- **Constraints** are negative exclusions only (what to avoid)
- This separation improves search query generation

**Note:** Requirements will evolve through conversation. The state should reflect the current understanding, updated as INTAKE learns more.

---

#### 2. Candidates

Products found by Explorer before enrichment.

| Concept | Intent | Example |
|---------|--------|---------|
| Product name | Identifier | "Fellow Stagg EKG" |
| Manufacturer | Who makes it | "Fellow" |
| Official URL | Canonical product page | URL to manufacturer's product page |
| Basic description | Summary from search | "Electric kettle with temperature control" |
| Category | Inferred product type | "electric kettle" |

**Note:** This is the raw list before Lattice enrichment. Should contain 20-50 candidates typically.

---

#### 3. Field Definitions

What dimensions to compare across candidates. These are dynamic based on product category and user priorities.

| Category | Intent | Example |
|---------|--------|---------|
| Standard fields | Always included | name, price, official_url |
| Category fields | Typical for this product type | capacity_litres, wattage (for kettles) |
| User-driven fields | Based on stated priorities | temperature_presets (if user mentioned it) |
| Qualification fields | Internal filters (not shown to user) | meets_requirements |

**Key behavior:** Explorer proposes field definitions based on:
- Product category norms (kettles → capacity, material, wattage)
- User's stated requirements (user said "build quality" → include material, warranty)
- What data is verifiable from official sources

**Field constraints:**
- Only verifiable, objective specifications allowed
- No subjective ratings (e.g., "handling_rating_out_of_10")
- No estimated costs (e.g., "maintenance_cost_estimate_per_year")
- List data type available for feature lists (e.g., "safety_features")

The AI should reason: *"For someone comparing kettles who cares about build quality, what verifiable specs would help them decide?"*

---

#### 4. Comparison Table (Living Table Architecture)

The enriched data: candidates × fields. Implemented as a "Living Table" with cell-level tracking for incremental updates.

| Concept | Intent |
|---------|--------|
| Rows | One per candidate (keyed by row_id, with deduplication) |
| Columns | Field definitions (standard + category + user-driven) |
| Cells | Individual cell with value, status, timestamp, and source |
| Metadata | Cell-level success/failure status |

**Cell Status Tracking:**

| Status | Meaning |
|--------|---------|
| PENDING | Cell needs enrichment |
| ENRICHED | Successfully enriched |
| FAILED | Enrichment failed (includes error message) |
| FLAGGED | User flagged for re-enrichment |

**Living Table Operations:**

| Operation | Behavior |
|-----------|----------|
| `add_row()` | Adds candidate with deduplication (by normalized name) |
| `add_field()` | Adds new field, marks all existing rows PENDING for that field |
| `update_cell()` | Updates specific cell value and status |
| `get_pending_cells()` | Returns cells needing enrichment (PENDING or FLAGGED) |
| `to_markdown()` | Renders table for display (truncates to max_rows) |
| `to_csv()` | Exports full table for download |

**Benefits of Living Table:**
- Incremental enrichment (only enrich what's changed)
- Field addition without re-enriching existing data
- Cell-level error tracking and retry
- Deduplication prevents duplicate products

**Note:** This is the primary output artifact. Exportable as CSV via the UI.

---

#### 5. Refinement History

Simple tracking of what changed across loops.

| Concept | Intent | Example |
|---------|--------|---------|
| Loop count | How many refinements | 2 |
| What changed | Brief description | "Added field: energy_efficiency" |
| Trigger | What the user said | "energy efficiency matters too" |

**Purpose:** Helps ADVISE understand context across refinements. Keeps explanations coherent ("As you requested, I've now added energy efficiency to the comparison...").

---

#### 6. Workflow Control

Flags that control routing and behavior.

| Concept | Intent |
|---------|--------|
| Current phase | Where we are in the workflow (intake, research, advise) |
| Need new search | Whether Explorer should run |
| New fields to add | Fields requested during refinement |
| Requested fields | Fields requested by user via ADVISE (for incremental addition) |
| Error state | If something failed, what and why |
| Advise has presented | Whether ADVISE has shown results to user (for mode switching) |

**HITL Control Flags:**

| Flag | Intent |
|------|--------|
| awaiting_requirements_confirmation | Paused for user to confirm requirements |
| awaiting_fields_confirmation | Paused for user to confirm field definitions before enrichment |
| awaiting_intent_confirmation | Paused for user to confirm refinement intent |
| action_choices | Button labels to display to user |
| pending_* | Temporary storage for data awaiting confirmation |

---

#### 7. Conversation History

The base template already provides message history. We reference it, not duplicate it.

| Concept | Intent |
|---------|--------|
| Messages | Full conversation (from base template) |

**Note:** All agents can see full conversation history. No additional conversation state needed unless we find gaps during implementation.

---

### State Lifecycle

```
Session Start
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  State initialized:                                 │
│  - Requirements: empty                              │
│  - Candidates: empty                                │
│  - Comparison table: empty                          │
│  - Phase: INTAKE                                    │
└─────────────────────────────────────────────────────┘
    │
    ▼ (INTAKE runs)
┌─────────────────────────────────────────────────────┐
│  State after INTAKE:                                │
│  - Requirements: populated                          │
│  - Phase: RESEARCH                                  │
└─────────────────────────────────────────────────────┘
    │
    ▼ (RESEARCH runs)
┌─────────────────────────────────────────────────────┐
│  State after RESEARCH:                              │
│  - Candidates: 20+ products                         │
│  - Field definitions: set                           │
│  - Comparison table: populated                      │
│  - Phase: ADVISE                                    │
└─────────────────────────────────────────────────────┘
    │
    ▼ (ADVISE runs, user refines)
┌─────────────────────────────────────────────────────┐
│  State after refinement:                            │
│  - Refinement history: updated                      │
│  - Need new search: true/false                      │
│  - New fields: if requested                         │
│  - Phase: RESEARCH or INTAKE                        │
└─────────────────────────────────────────────────────┘
    │
    ▼ (loop until user satisfied)
┌─────────────────────────────────────────────────────┐
│  Session End:                                       │
│  - User has selected product or ended session       │
└─────────────────────────────────────────────────────┘
```

---

### What We're NOT Defining Yet

- Exact field names and types (will emerge during implementation)
- Validation rules (will add as needed)
- Serialization format (handled by framework)
- Persistence strategy (single session, handled by base template)

---

## 5. Tools & Services

This section defines the tools and external services agents need to do their work.

---

### Tool Summary

| Tool | Used By | Purpose |
|------|---------|---------|
| Web Search | RESEARCH (Explorer) | Find product candidates |
| Lattice Enrichment | RESEARCH (Enricher) | Bulk data enrichment |
| Purchase Link Lookup | ADVISE | Find where to buy |
| CSV Export | ADVISE | Export comparison table |

---

### Web Search Tool

**Purpose:** Find product candidates matching user requirements.

**Input:**
- Search queries (10-15 diverse queries from SearchQueryPlan)
- Optional: filters, region, result count

**Output:**
- List of results: title, URL, snippet
- Source URLs from web_search_call.action
- Metadata: total results, search source

**Behavior:**
- Uses OpenAI o4-mini reasoning model for agentic search
- Reasoning model can perform multiple searches and visit pages
- Prioritizes official manufacturer pages over retailer/review sites
- URL validation filters out Amazon, eBay, review aggregators
- Extracts sources from both search results and open_page actions

**Service:** OpenAI Responses API with reasoning model (configurable via lattice_use_reasoning setting)

**Search Strategy Service:**
- Generates 10-15 diverse queries covering multiple angles
- Uses category knowledge base for authoritative sources
- Covers multiple brands and source types per search

---

### Lattice Enrichment Tool

**Purpose:** Bulk enrich candidates with structured comparison data via the Living Table.

**Input:**
- Living Table with PENDING cells (from state.living_table)
- Field definitions (already in Living Table)

**Output:**
- Updated Living Table with cells marked ENRICHED or FAILED
- Cell-level metadata: value, status, timestamp, source, error

**Behavior:**
- Uses Lattice library (vendor/lattice submodule)
- Web-enriched chain for real-time data extraction
- Async processing for performance
- Incremental enrichment: only processes PENDING/FLAGGED cells
- Updates cells individually, preserving existing enriched data

**Integration notes:**
- Field definitions must follow Lattice CSV schema
- Supports incremental field addition (only enriches new column)
- Handles partial failures at cell level (not row level)
- Respects max_products setting (default 30)

---

### Purchase Link Lookup Tool

**Purpose:** Find actual places to buy a selected product.

**Input:**
- Product name
- Official product URL
- Optional: region preference

**Output:**
- List of purchase links: retailer name, URL, price (if available)

**Behavior:**
- Search for product across known retailers
- Prioritize trusted/major retailers
- Include price if discoverable
- Return multiple options for comparison

**Note:** This is a simpler, targeted search—not bulk enrichment. Used when user has narrowed down to specific products.

---

### CSV Export Tool

**Purpose:** Export the comparison table for user download.

**Input:**
- Comparison table from state

**Output:**
- CSV file (or download link)

**Behavior:**
- Include all candidates (not just top 5)
- Include all fields
- Format suitable for spreadsheet import

---

### Services to Build

| Service | Priority | Notes |
|---------|----------|-------|
| Lattice integration wrapper | High | Adapter between workflow and Lattice library |
| Web search service | High | May use existing LLM service web search |
| Purchase link service | Medium | Can be simple web search initially |
| CSV export utility | Low | Straightforward data formatting |

---

## 6. Guardrails & Constraints

This section defines safety boundaries, error handling, and operational constraints.

---

### User Input Guardrails

| Guardrail | Rationale |
|-----------|-----------|
| Sanitize all user input | Prevent injection attacks |
| Reject requests for illegal products | Legal compliance |
| Handle off-topic requests gracefully | Stay on task without being rude |
| No personal data collection beyond session | Privacy |

---

### Search & Data Guardrails

| Guardrail | Rationale |
|-----------|-----------|
| Cap candidates at 50 | Control enrichment costs |
| Timeout on web searches | Prevent hanging |
| Validate URLs before storing | Data integrity |
| Flag potentially unreliable sources | Data quality |

---

### AI Behavior Guardrails

| Guardrail | Rationale |
|-----------|-----------|
| Don't invent product data | Accuracy—only use retrieved information |
| Acknowledge uncertainty | Don't claim confidence we don't have |
| Don't push specific products | Advisor, not salesperson |
| Disclose limitations | If data is incomplete, say so |

---

### Cost & Performance Constraints

| Constraint | Limit | Rationale |
|------------|-------|-----------|
| Max candidates per search | 30 (configurable via max_products) | Lattice enrichment cost |
| Max enrichment retries | 2 | Avoid infinite loops |
| Search timeout | 30 seconds | User experience |
| Enrichment timeout | 5 minutes | Large batch tolerance |
| Search queries per run | 10-15 | Diverse coverage without excessive API calls |

---

### Error Recovery Strategy

| Error Type | Recovery |
|------------|----------|
| Web search fails | Retry once with broader query; if still fails, inform user |
| Lattice fails partially | Continue with successful candidates, note incomplete data |
| Lattice fails completely | Inform user, offer to retry or adjust requirements |
| User intent unclear | Ask clarifying question before routing |
| State corruption | Log error, offer to start fresh |

---

### Session Boundaries

| Boundary | Behavior |
|----------|----------|
| Session timeout | Standard Chainlit session handling |
| No cross-session persistence | Each session starts fresh |
| No user accounts | Anonymous single-session use |

---

### Out of Scope (Explicitly)

These are NOT handled by Shortlist:

- Price tracking over time
- Purchase transactions
- User reviews or ratings submission
- Affiliate link optimization
- Multi-user collaboration
- Saved searches or wishlists
