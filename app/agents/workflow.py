"""LangGraph workflow definition and orchestration."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from app.agents.advise import advise_node
from app.agents.intake import intake_node
from app.agents.research import research_node
from app.models.state import AgentState
from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_hitl_message(content: str) -> tuple[str, str] | None:
    """
    Parse a HITL synthetic message.

    Args:
        content: Message content to parse

    Returns:
        Tuple of (checkpoint, choice) if valid HITL message, None otherwise
    """
    if not content.startswith("[HITL:"):
        return None
    # Format: [HITL:checkpoint:choice]
    try:
        inner = content[6:-1]  # Remove [HITL: and ]
        parts = inner.split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    except Exception as e:
        logger.debug(f"Failed to parse HITL message: {e}")
    return None


async def router_node(state: AgentState) -> Command:
    """
    Route incoming messages to the correct phase node.

    This router enables proper human-in-the-loop behavior by ensuring messages
    go to the node that should handle them based on current_phase, rather than
    always starting at INTAKE.

    Routing logic:
    - HITL messages → route to checkpoint-specific node
    - phase == "intake" or unset → intake node
    - phase == "advise" → advise node
    - phase == "research" → research node (edge case, shouldn't receive messages)

    Args:
        state: Current workflow state

    Returns:
        Command routing to the appropriate node
    """
    current_phase = state.get("current_phase", "intake")
    messages = state.get("messages", [])

    # Check for HITL synthetic message
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content"):
            hitl_parsed = parse_hitl_message(last_message.content)
            if hitl_parsed:
                checkpoint, choice = hitl_parsed
                logger.info(
                    f"Router: HITL message detected - checkpoint={checkpoint}, choice={choice}"
                )

                # Route based on checkpoint type
                if checkpoint == "requirements":
                    logger.info("Router: HITL directing to INTAKE")
                    return Command(goto="intake")
                elif checkpoint == "fields":
                    logger.info("Router: HITL directing to RESEARCH")
                    return Command(goto="research")
                elif checkpoint == "intent":
                    logger.info("Router: HITL directing to ADVISE")
                    return Command(goto="advise")

    logger.info(f"Router: current_phase={current_phase}")

    if current_phase == "advise":
        logger.info("Router: directing to ADVISE")
        return Command(goto="advise")
    elif current_phase == "research":
        # Edge case: user shouldn't send messages during research
        # but if they do, route to advise to handle it
        logger.info("Router: research phase, directing to ADVISE")
        return Command(goto="advise")
    else:
        # Default to intake for "intake" phase or any other state
        logger.info("Router: directing to INTAKE")
        return Command(goto="intake")


def create_workflow(llm_service: LLMService) -> StateGraph:
    """
    Create and compile the LangGraph workflow.

    The workflow follows Shortlist's 3-phase structure:
    INTAKE → RESEARCH → ADVISE → END

    With refinement loops:
    - ADVISE → RESEARCH (more options or new fields)
    - ADVISE → INTAKE (requirements changed)

    Human-in-the-loop:
    - INTAKE waits for user input each turn
    - RESEARCH runs automatically
    - ADVISE waits for user input each turn

    Args:
        llm_service: LLM service instance for model interactions

    Returns:
        Compiled LangGraph workflow
    """
    # Create graph with state schema
    graph = StateGraph(AgentState)

    # -------------------------------------------------------------------------
    # Add Nodes
    # -------------------------------------------------------------------------
    graph.add_node("router", router_node)
    graph.add_node("intake", intake_node)
    graph.add_node("research", research_node)
    graph.add_node("advise", advise_node)

    # -------------------------------------------------------------------------
    # Define Entry Point
    # -------------------------------------------------------------------------
    # All messages enter through the router, which directs to the correct
    # phase node based on current_phase. This enables proper human-in-the-loop
    # behavior where both INTAKE and ADVISE can receive user messages.
    graph.set_entry_point("router")

    # -------------------------------------------------------------------------
    # Edges are handled by Command API in each node
    # -------------------------------------------------------------------------
    # The router directs messages to the correct phase:
    # - router → intake (when phase == "intake")
    # - router → advise (when phase == "advise")
    #
    # Nodes use Command.goto for transitions:
    # - intake → research (when requirements ready)
    # - intake → __end__ (to wait for more user input)
    # - research → advise (when table ready)
    # - advise → __end__ (to wait for user input)
    # - advise → research (refinement: more options or new fields)
    # - advise → intake (refinement: requirements changed)

    # -------------------------------------------------------------------------
    # Compile with Memory
    # -------------------------------------------------------------------------
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)

    logger.info("Shortlist 3-phase workflow created and compiled")
    return compiled


class WorkflowResult:
    """Result from processing a message through the workflow."""

    def __init__(
        self,
        content: str,
        citations: list[dict] | None = None,
        sources: list[str] | None = None,
        # HITL state
        action_choices: list[str] | None = None,
        awaiting_requirements_confirmation: bool = False,
        awaiting_fields_confirmation: bool = False,
        awaiting_intent_confirmation: bool = False,
        # Phase tracking
        current_phase: str = "intake",
        # Living table data for UI rendering
        living_table: dict | None = None,
    ):
        self.content = content
        self.citations = citations or []
        self.sources = sources or []
        # HITL state
        self.action_choices = action_choices
        self.awaiting_requirements_confirmation = awaiting_requirements_confirmation
        self.awaiting_fields_confirmation = awaiting_fields_confirmation
        self.awaiting_intent_confirmation = awaiting_intent_confirmation
        # Phase tracking
        self.current_phase = current_phase
        # Living table data
        self.living_table = living_table


async def process_message(
    workflow: StateGraph,
    message: str,
    user_id: str,
    session_id: str,
) -> str:
    """
    Process a user message through the workflow.

    Args:
        workflow: Compiled LangGraph workflow
        message: User's message content
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        Assistant's response message
    """
    result = await process_message_with_state(workflow, message, user_id, session_id)
    return result.content


async def process_message_with_state(
    workflow: StateGraph,
    message: str,
    user_id: str,
    session_id: str,
) -> WorkflowResult:
    """
    Process a user message through the workflow and return full result.

    Args:
        workflow: Compiled LangGraph workflow
        message: User's message content
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        WorkflowResult with response content, citations, and sources
    """
    from langchain_core.messages import HumanMessage

    # Configure thread for memory persistence
    config = {"configurable": {"thread_id": session_id}}

    # Check if this is a new session by trying to get the current state
    try:
        current_state = await workflow.aget_state(config)
        is_new_session = not current_state.values  # Empty state means new session
    except Exception:
        is_new_session = True

    # Prepare input - only pass new message, let checkpointer handle rest
    if is_new_session:
        # First message: initialize full state
        input_state = {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "session_id": session_id,
            "current_phase": "intake",
            "current_node": "intake",
        }
        logger.info(f"Starting new session {session_id}")
    else:
        # Subsequent messages: only pass the new message
        # The checkpointer will merge this with existing state
        input_state = {
            "messages": [HumanMessage(content=message)],
        }
        logger.info(f"Continuing session {session_id}")

    # Run workflow
    try:
        result = await workflow.ainvoke(input_state, config)

        # Extract response from messages
        messages = result.get("messages", [])
        content = "I apologize, but I couldn't generate a response."
        if messages:
            last_message = messages[-1]
            content = last_message.content

        # Extract web search citations and sources
        citations = result.get("web_search_citations", [])
        sources = result.get("web_search_sources", [])

        # Extract HITL state
        action_choices = result.get("action_choices")
        awaiting_requirements = result.get("awaiting_requirements_confirmation", False)
        awaiting_fields = result.get("awaiting_fields_confirmation", False)
        awaiting_intent = result.get("awaiting_intent_confirmation", False)

        # Extract current phase
        current_phase = result.get("current_phase", "intake")

        # Extract living table data
        living_table = result.get("living_table")

        return WorkflowResult(
            content=content,
            citations=citations,
            sources=sources,
            action_choices=action_choices,
            awaiting_requirements_confirmation=awaiting_requirements,
            awaiting_fields_confirmation=awaiting_fields,
            awaiting_intent_confirmation=awaiting_intent,
            current_phase=current_phase,
            living_table=living_table,
        )

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return WorkflowResult(content=f"An error occurred while processing your request: {str(e)}")
