"""INTAKE node - Gather requirements through conversation."""

from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.models.state import AgentState
from app.services.llm import get_llm_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load prompt from YAML
PROMPTS_DIR = Path(__file__).parent / "prompts"
INTAKE_PROMPT_PATH = PROMPTS_DIR / "intake.yaml"

with open(INTAKE_PROMPT_PATH) as f:
    INTAKE_PROMPTS = yaml.safe_load(f)

INTAKE_SYSTEM_PROMPT = INTAKE_PROMPTS["system_prompt"]


class UserRequirements(BaseModel):
    """Structured user requirements extracted from conversation."""

    product_type: str | None = Field(
        None,
        description="The type/category of product the user wants (e.g., 'electric kettle', 'laptop', 'toaster')",
    )
    budget_min: float | None = Field(None, description="Minimum budget in the local currency")
    budget_max: float | None = Field(None, description="Maximum budget in the local currency")
    must_haves: list[str] = Field(
        default_factory=list,
        description="Non-negotiable features the product must have",
    )
    nice_to_haves: list[str] = Field(
        default_factory=list,
        description="Preferred features that are flexible",
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="What to optimize for (e.g., 'build quality', 'price', 'speed')",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="What to avoid (e.g., 'no plastic', 'not from X brand')",
    )


class IntakeDecision(BaseModel):
    """Decision about whether to proceed to research or continue gathering requirements."""

    requirements_sufficient: bool = Field(
        description="True if we have enough information to proceed to product research"
    )
    reasoning: str = Field(
        description="Brief explanation of why requirements are or aren't sufficient"
    )
    next_question: str | None = Field(
        None,
        description="If requirements insufficient, what question to ask the user next (conversational, not interrogating)",
    )


def format_requirements_summary(requirements: dict) -> str:
    """
    Format requirements into a human-readable summary for HITL confirmation.

    Args:
        requirements: User requirements dict

    Returns:
        Formatted summary string
    """
    parts = []

    product_type = requirements.get("product_type")
    if product_type:
        parts.append(f"**Product:** {product_type}")

    budget_min = requirements.get("budget_min")
    budget_max = requirements.get("budget_max")
    if budget_min and budget_max:
        parts.append(f"**Budget:** ${budget_min} - ${budget_max}")
    elif budget_max:
        parts.append(f"**Budget:** Under ${budget_max}")
    elif budget_min:
        parts.append(f"**Budget:** Over ${budget_min}")

    must_haves = requirements.get("must_haves", [])
    if must_haves:
        parts.append(f"**Must have:** {', '.join(must_haves)}")

    nice_to_haves = requirements.get("nice_to_haves", [])
    if nice_to_haves:
        parts.append(f"**Nice to have:** {', '.join(nice_to_haves)}")

    priorities = requirements.get("priorities", [])
    if priorities:
        parts.append(f"**Priorities:** {', '.join(priorities)}")

    constraints = requirements.get("constraints", [])
    if constraints:
        parts.append(f"**Avoid:** {', '.join(constraints)}")

    return "\n".join(parts) if parts else "No specific requirements captured."


def parse_hitl_choice(content: str) -> str | None:
    """
    Parse the choice from a HITL message.

    Args:
        content: Message content like "[HITL:requirements:Search Now]"

    Returns:
        The choice string or None if invalid
    """
    if not content.startswith("[HITL:"):
        return None
    try:
        inner = content[6:-1]  # Remove [HITL: and ]
        parts = inner.split(":", 1)
        if len(parts) == 2:
            return parts[1]
    except Exception:
        pass
    return None


def _clear_hitl_flags() -> dict:
    """Return a dict of cleared HITL flags for state updates."""
    return {
        "awaiting_requirements_confirmation": False,
        "awaiting_fields_confirmation": False,
        "awaiting_intent_confirmation": False,
        "action_choices": None,
        "pending_requirements_summary": None,
        "pending_field_definitions": None,
        "pending_intent": None,
        "pending_intent_details": None,
    }


async def intake_node(state: AgentState) -> Command:
    """
    INTAKE node - Gather user requirements through multi-turn conversation.

    This node engages in dialogue to understand what the user wants to buy.
    It uses LLM structured output to extract requirements and LLM judgment
    to determine when enough information has been gathered to proceed to RESEARCH.

    HITL Flow:
    - When requirements are sufficient, shows "Search Now" / "Edit Requirements" buttons
    - User must confirm before proceeding to expensive RESEARCH phase

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing decision
    """
    logger.info("INTAKE node processing")

    messages = state.get("messages", [])
    current_requirements = state.get("user_requirements") or {}

    # Check for HITL action at start
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content") and last_message.content.startswith(
            "[HITL:requirements:"
        ):
            choice = parse_hitl_choice(last_message.content)
            logger.info(f"INTAKE: HITL action received - {choice}")

            if choice == "Search Now":
                # User confirmed, proceed to research
                logger.info("INTAKE: User confirmed, transitioning to RESEARCH")
                return Command(
                    update={
                        "messages": [AIMessage(content="Starting the search now...")],
                        "current_node": "intake",
                        "current_phase": "research",
                        **_clear_hitl_flags(),
                    },
                    goto="research",
                )
            else:
                # User wants to edit requirements
                logger.info("INTAKE: User wants to edit requirements")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content="No problem! What would you like to change or add to your requirements?"
                            )
                        ],
                        "current_node": "intake",
                        "current_phase": "intake",
                        **_clear_hitl_flags(),
                    },
                    goto="__end__",
                )

    try:
        llm_service = get_llm_service()

        # Step 1: Extract requirements from conversation using structured output
        requirements_prompt = """Based on the entire conversation so far, extract the user's product requirements.

Update any previous requirements with new information from the latest messages.
If something hasn't been mentioned, leave it as None or empty list."""

        if current_requirements:
            requirements_prompt += f"\n\nPrevious requirements:\n{yaml.dump(current_requirements, default_flow_style=False)}"

        requirements_messages = messages.copy()
        requirements_messages.append(HumanMessage(content=requirements_prompt))

        extracted_requirements = await llm_service.generate_structured(
            requirements_messages,
            schema=UserRequirements,
            system_prompt=INTAKE_SYSTEM_PROMPT,
        )

        # Convert to dict and merge with current requirements
        updated_requirements = extracted_requirements.model_dump(exclude_none=True)

        # Merge lists properly (don't overwrite with empty lists)
        for key in ["must_haves", "nice_to_haves", "priorities", "constraints"]:
            if key in current_requirements and current_requirements[key]:
                if key not in updated_requirements or not updated_requirements[key]:
                    updated_requirements[key] = current_requirements[key]

        logger.info(f"Extracted requirements: {updated_requirements}")

        # Step 2: Ask LLM to decide if requirements are sufficient
        decision_prompt = f"""Based on the current requirements, decide if we have enough information to search for products.

Current requirements:
{yaml.dump(updated_requirements, default_flow_style=False)}

Minimum needed to proceed:
- Product type identified (what category of thing they want)
- At least one constraint (budget, must-have feature, or priority)

Consider the conversation flow - if the user seems ready to see results or has answered your clarifying questions, requirements might be sufficient."""

        decision_messages = messages.copy()
        decision_messages.append(HumanMessage(content=decision_prompt))

        decision = await llm_service.generate_structured(
            decision_messages,
            schema=IntakeDecision,
            system_prompt=INTAKE_SYSTEM_PROMPT,
        )

        logger.info(
            f"Decision: sufficient={decision.requirements_sufficient}, reasoning={decision.reasoning}"
        )

        # Step 3: Generate conversational response
        if decision.requirements_sufficient:
            # Ready to search - pause for HITL confirmation
            summary = format_requirements_summary(updated_requirements)
            confirmation_message = f"Here's what I found from our conversation:\n\n{summary}\n\nReady to search for products?"

            logger.info("INTAKE: Requirements sufficient, awaiting HITL confirmation")

            return Command(
                update={
                    "messages": [AIMessage(content=confirmation_message)],
                    "current_node": "intake",
                    "current_phase": "intake",  # Stay in intake until confirmed
                    "user_requirements": updated_requirements,
                    "awaiting_requirements_confirmation": True,
                    "pending_requirements_summary": summary,
                    "action_choices": ["Search Now", "Edit Requirements"],
                },
                goto="__end__",  # Return control to user for HITL
            )
        else:
            # Need more information - ask the next question
            if decision.next_question:
                response_content = decision.next_question
            else:
                # Fallback: generate a question
                question_prompt = f"""Generate a friendly follow-up question to gather more requirements.

Current requirements:
{yaml.dump(updated_requirements, default_flow_style=False)}

Ask about ONE specific thing that would help narrow down the search. Be conversational, not interrogating."""

                question_messages = messages.copy()
                question_messages.append(HumanMessage(content=question_prompt))

                llm_response = await llm_service.generate(
                    question_messages,
                    system_prompt=INTAKE_SYSTEM_PROMPT,
                )
                response_content = llm_response.content

            logger.info("Staying in INTAKE")

            return Command(
                update={
                    "messages": [AIMessage(content=response_content)],
                    "current_node": "intake",
                    "current_phase": "intake",
                    "user_requirements": updated_requirements,
                },
                goto="__end__",  # Return control to user for next input
            )

    except Exception:
        logger.exception("INTAKE error")
        return Command(
            update={
                "messages": [AIMessage(content="I encountered an error processing your request.")],
                "current_node": "intake",
                "current_phase": "error",
            },
            goto="__end__",
        )
