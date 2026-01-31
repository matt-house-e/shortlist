"""INTAKE node - Gather requirements through conversation."""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.models.state import AgentState
from app.services.llm import get_llm_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

INTAKE_SYSTEM_PROMPT = """You are a helpful shopping assistant helping users research products to buy.

Your role is to gather requirements through conversation:
- Understand what product category they're looking for
- Identify budget constraints
- Understand their priorities and must-have features
- Ask focused questions (max 2-3 per turn)
- Be conversational, not form-filling

Once you have:
1. Product type or category
2. At least one constraint (budget, feature, or preference)
3. User confirmation to search

Set "requirements_ready" to true in your response.

Keep the conversation natural and helpful. Offer sensible defaults when the user is uncertain."""


async def intake_node(state: AgentState) -> Command:
    """
    INTAKE node - Gather user requirements through multi-turn conversation.

    This node engages in dialogue to understand what the user wants to buy.
    It extracts requirements and determines when enough information has been
    gathered to proceed to the RESEARCH phase.

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing decision
    """
    logger.info("INTAKE node processing")

    messages = state.get("messages", [])

    try:
        llm_service = get_llm_service()

        # Generate response
        llm_response = await llm_service.generate(
            messages,
            system_prompt=INTAKE_SYSTEM_PROMPT,
        )

        # TODO: Parse requirements from LLM response
        # For now, we'll use a simple heuristic to determine if requirements are ready
        # In a full implementation, this would use structured outputs or function calling

        content = llm_response.content.lower()
        requirements_ready = False

        # Check if the user has confirmed readiness or if we have enough info
        if any(phrase in content for phrase in ["let's search", "ready to search", "start searching"]):
            requirements_ready = True

        # Determine next phase
        if requirements_ready:
            next_phase = "research"
            goto = "research"
            logger.info("Requirements ready, transitioning to RESEARCH")
        else:
            next_phase = "intake"
            goto="__end__"  # Return control to user for next input
            logger.info("Requirements incomplete, staying in INTAKE")

        return Command(
            update={
                "messages": [AIMessage(content=llm_response.content)],
                "current_node": "intake",
                "current_phase": next_phase,
            },
            goto=goto,
        )

    except Exception as e:
        logger.error(f"INTAKE error: {e}")
        return Command(
            update={
                "messages": [AIMessage(content=f"I encountered an error: {str(e)}")],
                "current_node": "intake",
                "phase": "error",
            },
            goto="__end__",
        )
