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
            table_context = f"\n\nComparison table available with {len(comparison_table.get('candidates', []))} products."

        # Generate response
        llm_response = await llm_service.generate(
            messages,
            system_prompt=ADVISE_SYSTEM_PROMPT + table_context,
        )

        # Parse user intent from the last user message
        last_user_message = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_user_message = msg.content.lower()
                break

        # TODO: Use structured LLM output for intent detection
        # For now, use simple heuristics on user message
        user_satisfied = any(phrase in last_user_message for phrase in ["done", "thank", "goodbye"])
        wants_more_options = "more options" in last_user_message or "find more" in last_user_message
        wants_new_fields = "add field" in last_user_message or "compare on" in last_user_message
        requirements_changed = "change requirement" in last_user_message or "actually my budget" in last_user_message

        # Determine routing
        need_new_search_flag = None  # Only set if routing to research
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
            need_new_search_flag = True
        elif wants_new_fields:
            logger.info("User wants new fields, returning to RESEARCH (Enricher only)")
            goto = "research"
            next_phase = "research"
            need_new_search_flag = False
        else:
            logger.info("Continuing conversation in ADVISE")
            goto = "__end__"  # Return control to user
            next_phase = "advise"

        # Build update dict
        update_dict = {
            "messages": [AIMessage(content=llm_response.content)],
            "current_node": "advise",
            "current_phase": next_phase,
        }

        # Add need_new_search flag if routing to research
        if need_new_search_flag is not None:
            update_dict["need_new_search"] = need_new_search_flag

        return Command(
            update=update_dict,
            goto=goto,
        )

    except Exception:
        logger.exception("ADVISE error")
        return Command(
            update={
                "messages": [AIMessage(content="I encountered an error processing your request.")],
                "current_node": "advise",
                "current_phase": "error",
            },
            goto="__end__",
        )
