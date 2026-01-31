"""LangGraph workflow definition and orchestration."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from app.agents.advise import advise_node
from app.agents.intake import intake_node
from app.agents.research import research_node
from app.models.state import AgentState
from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)


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
    graph.add_node("intake", intake_node)
    graph.add_node("research", research_node)
    graph.add_node("advise", advise_node)

    # -------------------------------------------------------------------------
    # Define Entry Point
    # -------------------------------------------------------------------------
    # All conversations start with INTAKE
    graph.set_entry_point("intake")

    # -------------------------------------------------------------------------
    # Edges are handled by Command API in each node
    # -------------------------------------------------------------------------
    # The nodes use Command.goto to dynamically route:
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
    ):
        self.content = content
        self.citations = citations or []
        self.sources = sources or []


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

    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": user_id,
        "session_id": session_id,
        "current_phase": "intake",
        "current_node": "intake",
    }

    # Configure thread for memory persistence
    config = {"configurable": {"thread_id": session_id}}

    # Run workflow
    logger.info(f"Processing message for session {session_id}")

    try:
        result = await workflow.ainvoke(initial_state, config)

        # Extract response from messages
        messages = result.get("messages", [])
        content = "I apologize, but I couldn't generate a response."
        if messages:
            last_message = messages[-1]
            content = last_message.content

        # Extract web search citations and sources
        citations = result.get("web_search_citations", [])
        sources = result.get("web_search_sources", [])

        return WorkflowResult(
            content=content,
            citations=citations,
            sources=sources,
        )

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return WorkflowResult(content=f"An error occurred while processing your request: {str(e)}")
