"""ADVISE node - Present recommendations and handle refinement."""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.models.state import AgentState
from app.services.llm import get_llm_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

ADVISE_SYSTEM_PROMPT = """You are a knowledgeable product advisor presenting research results.

Your role is to:
- Present the top 5 products from the comparison table
- Explain trade-offs clearly and honestly
- Highlight why each option made the list
- Don't push a single option; present choices
- Acknowledge data limitations

The user can:
- Ask follow-up questions
- Request purchase links
- Request CSV export
- Ask for more options (triggers new RESEARCH)
- Ask for new comparison fields (triggers ENRICHER only)
- Change requirements (returns to INTAKE)
- End the session

Analyze the user's intent and set the appropriate routing flag:
- "user_satisfied" = true → end session
- "wants_more_options" = true → new research needed
- "wants_new_fields" = true → enrichment only
- "requirements_changed" = true → back to intake
- Otherwise, stay in ADVISE to answer questions"""


async def advise_node(state: AgentState) -> Command:
    """
    ADVISE node - Present comparison results and handle refinement.

    This node shows recommendations, answers questions, and routes refinement
    requests to the appropriate phase.

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing decision
    """
    logger.info("ADVISE node processing")

    messages = state.get("messages", [])
    comparison_table = state.get("comparison_table")

    try:
        llm_service = get_llm_service()

        # Build context about the comparison table
        table_context = ""
        if comparison_table:
            table_context = f"\n\nComparison table available with {len(comparison_table.get('rows', []))} products."

        # Generate response
        llm_response = await llm_service.generate(
            messages,
            system_prompt=ADVISE_SYSTEM_PROMPT + table_context,
        )

        # TODO: Parse user intent from LLM response
        # For now, use simple heuristics
        content = llm_response.content.lower()

        user_satisfied = any(phrase in content for phrase in ["done", "thank", "goodbye"])
        wants_more_options = "more options" in content or "find more" in content
        wants_new_fields = "add field" in content or "compare on" in content
        requirements_changed = "change requirement" in content or "actually my budget" in content

        # Determine routing
        if user_satisfied:
            logger.info("User satisfied, ending session")
            goto = "__end__"
            next_phase = "complete"
        elif requirements_changed:
            logger.info("Requirements changed, returning to INTAKE")
            goto = "intake"
            next_phase = "intake"
        elif wants_more_options:
            logger.info("User wants more options, returning to RESEARCH")
            goto = "research"
            next_phase = "research"
            state["need_new_search"] = True
        elif wants_new_fields:
            logger.info("User wants new fields, returning to RESEARCH (Enricher only)")
            goto = "research"
            next_phase = "research"
            state["need_new_search"] = False
        else:
            logger.info("Continuing conversation in ADVISE")
            goto = "__end__"  # Return control to user
            next_phase = "advise"

        return Command(
            update={
                "messages": [AIMessage(content=llm_response.content)],
                "current_node": "advise",
                "current_phase": next_phase,
            },
            goto=goto,
        )

    except Exception as e:
        logger.error(f"ADVISE error: {e}")
        return Command(
            update={
                "messages": [AIMessage(content=f"I encountered an error: {str(e)}")],
                "current_node": "advise",
                "phase": "error",
            },
            goto="__end__",
        )
