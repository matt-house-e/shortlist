"""Router node - Entry point for the workflow."""

from langgraph.types import Command

from app.models.state import AgentState
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def router_node(state: AgentState) -> Command:
    """
    Route incoming requests to the appropriate agent.

    This is the entry point for the workflow. It analyzes the user's
    message and determines which agent should handle the request.

    For simple workflows, this might just pass through to a single agent.
    For complex workflows, implement routing logic here.

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and next node destination
    """
    logger.info("Router node processing request")

    # Get the latest user message
    messages = state.get("messages", [])
    if not messages:
        logger.warning("No messages in state")
        return Command(
            update={"phase": "error", "current_node": "router"},
            goto="agent",
        )

    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

    logger.info(f"Routing message: {user_input[:50]}...")

    # -------------------------------------------------------------------------
    # Routing Logic (Placeholder)
    # -------------------------------------------------------------------------
    # TODO: Implement your routing logic here
    #
    # Examples:
    # - Intent classification to route to specialized agents
    # - Keyword matching for specific workflows
    # - LLM-based routing decisions
    #
    # For now, we route everything to the main agent

    return Command(
        update={
            "phase": "processing",
            "current_node": "agent",
        },
        goto="agent",
    )
