"""LangGraph state schema - Central state for the workflow."""

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    Central state schema for the LangGraph workflow.

    This uses the "fat state" pattern where all workflow data lives in a single
    state object. This simplifies debugging and makes state transitions explicit.

    The state is divided into logical sections:
    - Message history (with LangGraph's add_messages reducer)
    - Workflow control (phase, current node)
    - User context (identifiers, metadata)
    - Domain-specific fields (add your own)

    Usage:
        state = AgentState(
            messages=[HumanMessage(content="Hello")],
            user_id="user123",
            phase="start",
        )
    """

    # =========================================================================
    # Message History
    # =========================================================================
    # Using add_messages reducer for proper message handling
    messages: Annotated[list[BaseMessage], add_messages]

    # =========================================================================
    # Workflow Control
    # =========================================================================
    # Current phase of the workflow
    phase: str  # start, processing, complete, error

    # Current node being executed
    current_node: str

    # =========================================================================
    # User Context
    # =========================================================================
    # User identifier (from auth)
    user_id: str

    # Chat session identifier
    session_id: str

    # User metadata (expanded from auth provider)
    user_metadata: dict[str, Any]

    # =========================================================================
    # Turn Metrics
    # =========================================================================
    # Cumulative token usage across conversation
    cumulative_prompt_tokens: int
    cumulative_completion_tokens: int

    # Turn tracking
    turn_number: int

    # Last LLM response time in seconds
    last_llm_response_time: float

    # Workflow tracking
    workflow_id: str

    # Chainlit thread ID (for persistence)
    chainlit_thread_id: str

    # =========================================================================
    # Web Search Results
    # =========================================================================
    # Citations from web search (accumulates across turns)
    web_search_citations: Annotated[list[dict], operator.add]

    # Source URLs consulted during web search
    web_search_sources: Annotated[list[str], operator.add]

    # OpenAI Responses API ID for conversation continuity
    openai_response_id: str | None

    # =========================================================================
    # Domain-Specific Fields (Shortlist)
    # =========================================================================
    # User requirements for product search
    user_requirements: dict[str, Any] | None

    # Product candidates (raw list from explorer, before enrichment)
    candidates: list[dict[str, Any]]

    # Living comparison table - single source of truth for product data
    # This is a serialized ComparisonTable Pydantic model
    living_table: dict[str, Any] | None

    # DEPRECATED: Legacy comparison table, kept for migration
    # Use living_table instead
    comparison_table: dict[str, Any] | None

    # Refinement history
    refinement_history: list[dict[str, Any]]

    # Workflow control flags
    need_new_search: bool
    new_fields_to_add: list[str]
    current_phase: str  # intake, research, advise

    # Fields requested by user via ADVISE (for incremental field addition)
    # RESEARCH reads this to add only new fields without regenerating everything
    requested_fields: list[str]

    # Track whether ADVISE has presented results to user
    # Used to distinguish first entry (present results) vs subsequent (analyze intent)
    advise_has_presented: bool

    # =========================================================================
    # Human-in-the-Loop (HITL) Control
    # =========================================================================
    # Confirmation flags - indicate workflow is paused awaiting user action
    awaiting_requirements_confirmation: bool
    awaiting_fields_confirmation: bool
    awaiting_intent_confirmation: bool

    # UI action choices - buttons to display to user
    action_choices: list[str] | None

    # Pending data awaiting confirmation
    pending_requirements_summary: str | None
    pending_field_definitions: list[dict[str, Any]] | None
    pending_intent: str | None
    pending_intent_details: dict[str, Any] | None


# =============================================================================
# State Helpers
# =============================================================================


def create_initial_state(
    user_id: str,
    session_id: str,
    user_metadata: dict[str, Any] | None = None,
    workflow_id: str | None = None,
    chainlit_thread_id: str | None = None,
) -> AgentState:
    """
    Create an initial state for a new conversation.

    Args:
        user_id: User identifier
        session_id: Session identifier
        user_metadata: Optional user metadata
        workflow_id: Optional workflow identifier
        chainlit_thread_id: Optional Chainlit thread ID for persistence

    Returns:
        Initial AgentState
    """
    import uuid

    return AgentState(
        messages=[],
        phase="start",
        current_node="intake",
        user_id=user_id,
        session_id=session_id,
        user_metadata=user_metadata or {},
        cumulative_prompt_tokens=0,
        cumulative_completion_tokens=0,
        turn_number=0,
        last_llm_response_time=0.0,
        workflow_id=workflow_id or str(uuid.uuid4()),
        chainlit_thread_id=chainlit_thread_id or "",
        web_search_citations=[],
        web_search_sources=[],
        openai_response_id=None,
        # Shortlist-specific fields
        user_requirements=None,
        candidates=[],
        living_table=None,
        comparison_table=None,  # DEPRECATED: kept for migration
        refinement_history=[],
        need_new_search=False,
        new_fields_to_add=[],
        requested_fields=[],
        current_phase="intake",
        # HITL fields
        awaiting_requirements_confirmation=False,
        awaiting_fields_confirmation=False,
        awaiting_intent_confirmation=False,
        action_choices=None,
        pending_requirements_summary=None,
        pending_field_definitions=None,
        pending_intent=None,
        pending_intent_details=None,
    )
