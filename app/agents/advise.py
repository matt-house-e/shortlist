"""ADVISE node - Present recommendations and handle refinement."""

import json

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

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
- End the session"""


class UserIntent(BaseModel):
    """Detected user intent from their message in ADVISE phase."""

    intent_type: str = Field(
        description="The primary intent: 'satisfied' (done/ending), 'more_options' (find more products), 'new_fields' (add comparison dimensions), 'change_requirements' (modify search criteria), 'question' (asking for clarification)"
    )
    reasoning: str = Field(description="Brief explanation of why this intent was detected")
    extracted_fields: list[str] = Field(
        default_factory=list,
        description="If intent is 'new_fields', the specific fields user wants to add (e.g., ['energy efficiency', 'warranty'])",
    )


async def advise_node(state: AgentState) -> Command:
    """
    ADVISE node - Present comparison results and handle refinement.

    This node has two modes:
    1. First entry (from RESEARCH): Present results and wait for user input
    2. Subsequent entries (user sent message): Analyze intent and route

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing decision
    """
    logger.info("ADVISE node processing")

    messages = state.get("messages", [])
    comparison_table = state.get("comparison_table")
    requirements = state.get("user_requirements", {})
    has_presented = state.get("advise_has_presented", False)

    try:
        llm_service = get_llm_service()

        # Build context with actual comparison data (not just count)
        table_context = ""
        if comparison_table and comparison_table.get("candidates"):
            candidates = comparison_table.get("candidates", [])
            fields = comparison_table.get("fields", [])

            # Include top 5 candidates with key fields
            top_candidates = candidates[:5]
            table_data = {
                "total_candidates": len(candidates),
                "fields": fields,
                "top_5_products": top_candidates,
            }

            table_context = f"\n\nComparison Table Data:\n{json.dumps(table_data, indent=2, ensure_ascii=False)}"

        # Add requirements context
        requirements_context = ""
        if requirements:
            requirements_context = (
                f"\n\nUser Requirements:\n{json.dumps(requirements, indent=2, ensure_ascii=False)}"
            )

        # -------------------------------------------------------------------
        # First entry: Present results and wait for user input
        # -------------------------------------------------------------------
        if not has_presented:
            logger.info("ADVISE: First entry - presenting results")

            # Generate presentation of results
            llm_response = await llm_service.generate(
                messages,
                system_prompt=ADVISE_SYSTEM_PROMPT + table_context + requirements_context,
            )

            return Command(
                update={
                    "messages": [AIMessage(content=llm_response.content)],
                    "current_node": "advise",
                    "current_phase": "advise",
                    "advise_has_presented": True,
                },
                goto="__end__",  # Wait for user input
            )

        # -------------------------------------------------------------------
        # Subsequent entry: User sent a new message, analyze intent
        # -------------------------------------------------------------------
        logger.info("ADVISE: Analyzing user intent")

        # Get the user's latest message
        last_user_message = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "human":
                last_user_message = msg.content
                break

        if not last_user_message:
            # Edge case: no user message found, just respond
            logger.warning("ADVISE: No user message found, generating response")
            llm_response = await llm_service.generate(
                messages,
                system_prompt=ADVISE_SYSTEM_PROMPT + table_context + requirements_context,
            )
            return Command(
                update={
                    "messages": [AIMessage(content=llm_response.content)],
                    "current_node": "advise",
                    "current_phase": "advise",
                },
                goto="__end__",
            )

        # Detect user intent
        intent_prompt = f"""Analyze the user's last message to determine their intent.

User's message: "{last_user_message}"

Current phase: We have presented product recommendations and the user is now responding.

Possible intents:
- 'satisfied': User is done and happy with results (e.g., "thanks", "I'll go with this", "that's all")
- 'more_options': User wants to see more products (e.g., "show me more", "any other options?")
- 'new_fields': User wants to add comparison dimensions (e.g., "can you add energy efficiency?", "compare warranty")
- 'change_requirements': User wants to modify search criteria (e.g., "actually my budget is £30", "I want a different brand")
- 'question': User is asking a follow-up question about current results

What is their primary intent?"""

        intent_messages = messages.copy()
        intent_messages.append(HumanMessage(content=intent_prompt))

        user_intent = await llm_service.generate_structured(
            intent_messages,
            schema=UserIntent,
            system_prompt=ADVISE_SYSTEM_PROMPT,
        )

        logger.info(
            f"Detected intent: {user_intent.intent_type}, reasoning: {user_intent.reasoning}"
        )

        # Generate conversational response
        llm_response = await llm_service.generate(
            messages,
            system_prompt=ADVISE_SYSTEM_PROMPT + table_context + requirements_context,
        )

        # Determine routing based on intent
        need_new_search_flag = None
        reset_presented_flag = False

        if user_intent.intent_type == "satisfied":
            logger.info("User satisfied, ending session")
            goto = "__end__"
            next_phase = "complete"
        elif user_intent.intent_type == "change_requirements":
            logger.info("Requirements changed, returning to INTAKE")
            goto = "intake"
            next_phase = "intake"
            reset_presented_flag = True
        elif user_intent.intent_type == "more_options":
            logger.info("User wants more options, returning to RESEARCH")
            goto = "research"
            next_phase = "research"
            need_new_search_flag = True
            reset_presented_flag = True
        elif user_intent.intent_type == "new_fields":
            logger.info(
                f"User wants new fields: {user_intent.extracted_fields}, returning to RESEARCH (Enricher only)"
            )
            goto = "research"
            next_phase = "research"
            need_new_search_flag = False
            reset_presented_flag = True
        else:  # question or uncertain
            logger.info("Continuing conversation in ADVISE")
            goto = "__end__"
            next_phase = "advise"

        # Build update dict
        update_dict = {
            "messages": [AIMessage(content=llm_response.content)],
            "current_node": "advise",
            "current_phase": next_phase,
        }

        # Reset the presented flag if we're leaving ADVISE
        if reset_presented_flag:
            update_dict["advise_has_presented"] = False

        # Add need_new_search flag if routing to research
        if need_new_search_flag is not None:
            update_dict["need_new_search"] = need_new_search_flag

        # Add new fields if detected
        if user_intent.intent_type == "new_fields" and user_intent.extracted_fields:
            update_dict["requested_fields"] = user_intent.extracted_fields

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
