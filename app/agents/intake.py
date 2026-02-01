"""INTAKE node - Gather requirements through conversation."""

from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.models.state import AgentState
from app.services.llm import get_intake_llm_service, get_llm_service
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
        description="The type/category of product the user wants (e.g., 'electric kettle', 'laptop', 'sports car')",
    )
    budget_min: float | None = Field(None, description="Minimum budget in the local currency")
    budget_max: float | None = Field(None, description="Maximum budget in the local currency")
    must_haves: list[str] = Field(
        default_factory=list,
        description="Non-negotiable features the product must have (e.g., 'fast', 'good handling', 'variable temperature')",
    )
    nice_to_haves: list[str] = Field(
        default_factory=list,
        description="Preferred features that are flexible (e.g., 'leather seats', 'bluetooth')",
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="What to optimize for, in order of importance (e.g., 'speed', 'handling', 'daily usability')",
    )
    specifications: list[str] = Field(
        default_factory=list,
        description="Positive specifications that narrow the search scope - condition, age, location, type (e.g., 'second hand', 'year 2010-2020', 'UK market', 'manual transmission', 'coupe or convertible')",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Things to explicitly AVOID - negative requirements only (e.g., 'no German cars', 'avoid high mileage over 100k', 'not automatic')",
    )


class IntakeDecision(BaseModel):
    """Decision about how to continue the intake conversation."""

    user_asked_question: bool = Field(
        default=False,
        description="True if the user's last message was asking for information/clarification (e.g., 'What is OLED?', 'What's the difference between...')",
    )
    user_ready_to_search: bool = Field(
        default=False,
        description="True if the user explicitly wants to proceed to search (e.g., 'search now', 'show me options', 'let's see what you find')",
    )
    response: str = Field(
        description="Your response to the user. If they asked a question, answer it educationally. Otherwise, acknowledge their input and suggest a relevant consideration or ask a clarifying question.",
    )
    suggested_consideration: str | None = Field(
        None,
        description="A product-specific consideration to mention (e.g., 'panel type for TVs', 'noise cancelling for headphones'). Only include if naturally relevant to the conversation.",
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

    specifications = requirements.get("specifications", [])
    if specifications:
        parts.append(f"**Specifications:** {', '.join(specifications)}")

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

            if choice in ("Search Now", "Ready to Search"):
                # User confirmed, proceed to research
                logger.info("INTAKE: User confirmed, transitioning to RESEARCH")
                return Command(
                    update={
                        "messages": [AIMessage(content="Starting the search now...")],
                        "current_node": "intake",
                        "current_phase": "research",
                        "user_requirements": current_requirements,
                        **_clear_hitl_flags(),
                    },
                    goto="research",
                )
            else:
                # User wants to continue refining (shouldn't happen with current UI, but handle gracefully)
                logger.info("INTAKE: User wants to continue refining")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content="No problem! What else would you like to tell me about what you're looking for?"
                            )
                        ],
                        "current_node": "intake",
                        "current_phase": "intake",
                        **_clear_hitl_flags(),
                    },
                    goto="__end__",
                )

    try:
        # Use GPT-4.1 for requirement extraction (better at nuanced understanding)
        intake_llm = get_intake_llm_service()
        # Keep standard LLM for conversational responses
        llm_service = get_llm_service()

        # Step 1: Extract requirements from conversation using structured output
        requirements_prompt = """Based on the entire conversation so far, extract the user's product requirements.

Update any previous requirements with new information from the latest messages.
If something hasn't been mentioned, leave it as None or empty list."""

        if current_requirements:
            requirements_prompt += f"\n\nPrevious requirements:\n{yaml.dump(current_requirements, default_flow_style=False)}"

        requirements_messages = messages.copy()
        requirements_messages.append(HumanMessage(content=requirements_prompt))

        extracted_requirements = await intake_llm.generate_structured(
            requirements_messages,
            schema=UserRequirements,
            system_prompt=INTAKE_SYSTEM_PROMPT,
        )

        # Convert to dict and merge with current requirements
        updated_requirements = extracted_requirements.model_dump(exclude_none=True)

        # Merge lists properly (don't overwrite with empty lists)
        for key in ["must_haves", "nice_to_haves", "priorities", "specifications", "constraints"]:
            if key in current_requirements and current_requirements[key]:
                if key not in updated_requirements or not updated_requirements[key]:
                    updated_requirements[key] = current_requirements[key]

        logger.info(f"Extracted requirements: {updated_requirements}")

        # Step 2: Generate conversational response with contextual suggestions
        # Check if we have minimum viable requirements (product type known)
        has_product_type = bool(updated_requirements.get("product_type"))

        decision_prompt = f"""Analyze the user's last message and generate an appropriate response.

Current requirements:
{yaml.dump(updated_requirements, default_flow_style=False)}

Your task:
1. If the user asked a question (e.g., "What is OLED?", "What's the difference between..."), answer it educationally with practical trade-offs.
2. If the user provided new information, acknowledge it and either:
   - Suggest a relevant consideration they might not have thought about (e.g., "Have you considered panel type?" for TVs)
   - Ask a clarifying question that would meaningfully affect their choice
3. If the user explicitly wants to search ("show me options", "let's search", "I'm ready"), set user_ready_to_search to true.

Be a knowledgeable consultant—proactively helpful, not just reactive. Don't ask multiple questions at once."""

        decision_messages = messages.copy()
        decision_messages.append(HumanMessage(content=decision_prompt))

        decision = await llm_service.generate_structured(
            decision_messages,
            schema=IntakeDecision,
            system_prompt=INTAKE_SYSTEM_PROMPT,
        )

        logger.info(
            f"Decision: user_ready={decision.user_ready_to_search}, asked_question={decision.user_asked_question}"
        )

        # If user explicitly wants to search, proceed to research
        if decision.user_ready_to_search:
            logger.info("INTAKE: User ready to search, transitioning to RESEARCH")
            return Command(
                update={
                    "messages": [AIMessage(content="Starting the search now...")],
                    "current_node": "intake",
                    "current_phase": "research",
                    "user_requirements": updated_requirements,
                    **_clear_hitl_flags(),
                },
                goto="research",
            )

        # Build response - continue conversational intake
        response_content = decision.response

        # Show "Ready to Search" escape hatch once we know the product type
        # This lets users proceed whenever they want, without waiting for the agent to decide
        if has_product_type:
            logger.info("INTAKE: Product type known, showing escape hatch button")
            return Command(
                update={
                    "messages": [AIMessage(content=response_content)],
                    "current_node": "intake",
                    "current_phase": "intake",
                    "user_requirements": updated_requirements,
                    "awaiting_requirements_confirmation": True,
                    "action_choices": ["Ready to Search"],
                },
                goto="__end__",
            )
        else:
            # Still gathering basic info (no product type yet)
            logger.info("Staying in INTAKE, gathering product type")
            return Command(
                update={
                    "messages": [AIMessage(content=response_content)],
                    "current_node": "intake",
                    "current_phase": "intake",
                    "user_requirements": updated_requirements,
                },
                goto="__end__",
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
