"""ADVISE node - Present recommendations and handle refinement."""

import json

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.models.schemas.shortlist import ComparisonTable
from app.models.state import AgentState
from app.services.llm import get_llm_service
from app.utils.hitl import clear_hitl_flags, parse_hitl_choice
from app.utils.logger import get_logger

logger = get_logger(__name__)

ADVISE_SYSTEM_PROMPT = """You are a product advisor presenting research results. The comparison table is displayed separately - your job is to ADD INSIGHT, not repeat data.

## Response Format (use this structure)

### My Pick: [Product Name] ($X)
One sentence explaining why this best matches their criteria.

---

### Quick Comparison
| | Best For | Trade-off |
|---|---|---|
| **[Product 1]** | [key strength] | [main weakness] |
| **[Product 2]** | [key strength] | [main weakness] |
| **[Product 3]** | [key strength] | [main weakness] |

### Beyond the Top 3
Use the full product list to surface valuable alternatives:
- **Best Value**: [Product] at $X offers [benefit] if [trade-off is acceptable]
- **If Budget Stretches**: [Product] at $X adds [compelling feature]
- **Budget-Friendly**: [Product] at $X still delivers [core need]

Only include sections that are genuinely useful based on the data.

---

**[End with 1-2 specific follow-up options relevant to their search]**

## Rules
- NEVER list specs (price, battery mAh, camera MP) - the table shows these
- DO compare and contrast - help them DECIDE
- Use **bold** for product names and key decision points
- Use horizontal rules (---) to create visual sections
- Keep it scannable - busy users skim
- Be honest about trade-offs and data gaps

The user can ask follow-up questions, request purchase links/CSV export, ask for more options, add comparison fields, or change requirements."""


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


def _get_intent_description(intent_type: str, extracted_fields: list[str] | None = None) -> str:
    """
    Get a human-readable description of the detected intent.

    Args:
        intent_type: The detected intent type
        extracted_fields: Optional list of fields for new_fields intent

    Returns:
        Human-readable description
    """
    descriptions = {
        "more_options": "It sounds like you'd like me to search for more product options.",
        "new_fields": f"I'll add {', '.join(extracted_fields) if extracted_fields else 'new fields'} to the comparison.",
        "change_requirements": "I understand you'd like to modify your search criteria.",
    }
    return descriptions.get(intent_type, "I'll help you with that.")


async def _execute_confirmed_intent(
    state: AgentState,
    pending_intent: str,
    pending_details: dict | None,
) -> Command:
    """
    Execute a confirmed intent action.

    Args:
        state: Current workflow state
        pending_intent: The confirmed intent type
        pending_details: Details about the intent (e.g., extracted fields)

    Returns:
        Command with routing to the appropriate node
    """
    logger.info(f"ADVISE: Executing confirmed intent - {pending_intent}")

    if pending_intent == "more_options":
        return Command(
            update={
                "messages": [AIMessage(content="Starting a new search for more options...")],
                "current_node": "advise",
                "current_phase": "research",
                "need_new_search": True,
                "advise_has_presented": False,
                **clear_hitl_flags(),
            },
            goto="research",
        )
    elif pending_intent == "new_fields":
        extracted_fields = pending_details.get("extracted_fields", []) if pending_details else []
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content=f"Adding {', '.join(extracted_fields) if extracted_fields else 'new fields'} to the comparison..."
                    )
                ],
                "current_node": "advise",
                "current_phase": "research",
                "need_new_search": False,
                "advise_has_presented": False,
                "requested_fields": extracted_fields,
                **clear_hitl_flags(),
            },
            goto="research",
        )
    elif pending_intent == "change_requirements":
        return Command(
            update={
                "messages": [
                    AIMessage(
                        content="Let's update your requirements. What would you like to change?"
                    )
                ],
                "current_node": "advise",
                "current_phase": "intake",
                "advise_has_presented": False,
                **clear_hitl_flags(),
            },
            goto="intake",
        )
    else:
        # Fallback
        return Command(
            update={
                "messages": [
                    AIMessage(content="I'm not sure what action to take. Can you clarify?")
                ],
                "current_node": "advise",
                "current_phase": "advise",
                **clear_hitl_flags(),
            },
            goto="__end__",
        )


async def advise_node(state: AgentState) -> Command:
    """
    ADVISE node - Present comparison results and handle refinement.

    This node has three modes:
    1. First entry (from RESEARCH): Present results and wait for user input
    2. HITL confirmation: User confirms detected intent before routing
    3. Subsequent entries (user sent message): Analyze intent and route

    HITL Flow:
    - When intent requires action (more_options, new_fields, change_requirements),
      shows "Yes, proceed" / "No, let me clarify" buttons
    - User must confirm before expensive operations

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
    awaiting_intent = state.get("awaiting_intent_confirmation", False)

    # Check for HITL action at start
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content") and last_message.content.startswith("[HITL:intent:"):
            choice = parse_hitl_choice(last_message.content)
            logger.info(f"ADVISE: HITL action received - {choice}")

            pending_intent = state.get("pending_intent")
            pending_details = state.get("pending_intent_details")

            if choice == "Yes, proceed":
                # User confirmed, execute the intent
                return await _execute_confirmed_intent(state, pending_intent, pending_details)
            else:
                # User wants to clarify
                logger.info("ADVISE: User wants to clarify")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content="No problem! Please tell me more about what you'd like to do."
                            )
                        ],
                        "current_node": "advise",
                        "current_phase": "advise",
                        **clear_hitl_flags(),
                    },
                    goto="__end__",
                )

    # Check if awaiting confirmation but user typed something instead
    if awaiting_intent and messages:
        last_message = messages[-1]
        if hasattr(last_message, "content") and not last_message.content.startswith("[HITL:"):
            # User typed instead of clicking - treat as clarification
            logger.info(
                "ADVISE: User provided text while awaiting intent confirmation - treating as clarification"
            )
            # Clear HITL flags and continue with normal intent detection
            # Fall through to normal processing below

    try:
        llm_service = get_llm_service()

        # Build context with actual comparison data
        # Prefer living_table if available, fall back to legacy comparison_table
        table_context = ""
        living_table_data = state.get("living_table")

        if living_table_data:
            # Use the new living table format
            living_table = ComparisonTable.model_validate(living_table_data)
            field_names = living_table.get_field_names(exclude_internal=True)

            # Build candidates data from living table - include more for comparative insights
            all_candidates = []
            for row in living_table.rows.values():
                candidate_data = {
                    "name": row.candidate.name,
                    "manufacturer": row.candidate.manufacturer,
                }
                # Add enriched field values
                for field_name in field_names:
                    cell = row.cells.get(field_name)
                    if cell and cell.value is not None:
                        candidate_data[field_name] = cell.value
                all_candidates.append(candidate_data)

            # Provide top 5 for main recommendation + additional products for comparative insights
            table_data = {
                "total_candidates": living_table.get_row_count(),
                "qualified_candidates": len(living_table.get_qualified_rows()),
                "fields": field_names,
                "top_5_products": all_candidates[:5],
                "additional_products": all_candidates[
                    5:15
                ],  # Next 10 for "stretch budget", "best value" insights
            }

            table_context = f"\n\nComparison Table Data:\n{json.dumps(table_data, indent=2, ensure_ascii=False)}"

            # Also include markdown table for easy reference (top 5 only)
            markdown_table = living_table.to_markdown(max_rows=5)
            table_context += f"\n\nTable Preview (top 5):\n{markdown_table}"

        elif comparison_table and comparison_table.get("candidates"):
            # Fall back to legacy comparison_table
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
                    **clear_hitl_flags(),
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
                # Skip HITL synthetic messages
                if not msg.content.startswith("[HITL:"):
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
                    **clear_hitl_flags(),
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

        # Check if intent requires HITL confirmation
        if user_intent.intent_type in ["more_options", "new_fields", "change_requirements"]:
            # Pause for HITL confirmation
            intent_desc = _get_intent_description(
                user_intent.intent_type,
                user_intent.extracted_fields,
            )
            confirmation_message = f"{intent_desc}\n\nIs this what you'd like?"

            logger.info(f"ADVISE: Intent requires confirmation - {user_intent.intent_type}")

            return Command(
                update={
                    "messages": [AIMessage(content=confirmation_message)],
                    "current_node": "advise",
                    "current_phase": "advise",
                    "awaiting_intent_confirmation": True,
                    "pending_intent": user_intent.intent_type,
                    "pending_intent_details": {"extracted_fields": user_intent.extracted_fields},
                    "action_choices": ["Yes, proceed", "No, let me clarify"],
                },
                goto="__end__",  # Wait for HITL confirmation
            )

        # For satisfied and question intents, no confirmation needed
        if user_intent.intent_type == "satisfied":
            logger.info("User satisfied, ending session")

            # Generate a farewell response
            llm_response = await llm_service.generate(
                messages,
                system_prompt=ADVISE_SYSTEM_PROMPT + table_context + requirements_context,
            )

            return Command(
                update={
                    "messages": [AIMessage(content=llm_response.content)],
                    "current_node": "advise",
                    "current_phase": "complete",
                    **clear_hitl_flags(),
                },
                goto="__end__",
            )
        else:
            # Question or uncertain - continue conversation
            logger.info("Continuing conversation in ADVISE")

            llm_response = await llm_service.generate(
                messages,
                system_prompt=ADVISE_SYSTEM_PROMPT + table_context + requirements_context,
            )

            return Command(
                update={
                    "messages": [AIMessage(content=llm_response.content)],
                    "current_node": "advise",
                    "current_phase": "advise",
                    **clear_hitl_flags(),
                },
                goto="__end__",
            )

    except Exception:
        logger.exception("ADVISE error")
        return Command(
            update={
                "messages": [AIMessage(content="I encountered an error processing your request.")],
                "current_node": "advise",
                "current_phase": "error",
                **clear_hitl_flags(),
            },
            goto="__end__",
        )
