"""INTAKE node - Gather requirements through conversation."""

from pathlib import Path

import yaml
from langchain_core.messages import AIMessage
from langgraph.types import Command

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


def parse_requirements(content: str, current_requirements: dict | None) -> dict:
    """
    Parse requirements from conversation.

    This is a simple heuristic parser. In production, this would use
    structured output from the LLM (function calling or structured JSON).

    Args:
        content: LLM response content
        current_requirements: Existing requirements to update

    Returns:
        Updated requirements dictionary
    """
    requirements = current_requirements or {}

    # Extract budget mentions (simple pattern matching)
    content_lower = content.lower()

    # Look for budget patterns
    if "under" in content_lower or "below" in content_lower:
        # Try to extract number - this is simplified
        words = content_lower.split()
        for i, word in enumerate(words):
            if word in ["under", "below", "max"] and i + 1 < len(words):
                next_word = words[i + 1].replace("£", "").replace("$", "")
                try:
                    requirements["budget_max"] = float(next_word)
                except ValueError:
                    pass

    # Look for product type mentions
    if "kettle" in content_lower:
        requirements["product_type"] = "electric kettle"
    elif "laptop" in content_lower:
        requirements["product_type"] = "laptop"
    elif "car" in content_lower:
        requirements["product_type"] = "car"

    # Look for priorities
    if "build quality" in content_lower or "quality" in content_lower:
        if "priorities" not in requirements:
            requirements["priorities"] = []
        if "build quality" not in requirements["priorities"]:
            requirements["priorities"].append("build quality")

    if "price" in content_lower or "value" in content_lower or "affordable" in content_lower:
        if "priorities" not in requirements:
            requirements["priorities"] = []
        if "price" not in requirements["priorities"]:
            requirements["priorities"].append("price")

    return requirements


def requirements_are_complete(requirements: dict | None) -> bool:
    """
    Check if requirements are sufficient to proceed to RESEARCH.

    Minimum requirements:
    1. Product type identified
    2. At least one constraint (budget, must_have, priority, etc.)

    Args:
        requirements: Requirements dictionary

    Returns:
        True if requirements are complete enough to search
    """
    if not requirements:
        return False

    # Must have product type
    if not requirements.get("product_type"):
        return False

    # Must have at least one constraint
    has_budget = requirements.get("budget_min") or requirements.get("budget_max")
    has_must_haves = bool(requirements.get("must_haves", []))
    has_priorities = bool(requirements.get("priorities", []))
    has_constraints = bool(requirements.get("constraints", []))

    has_constraint = has_budget or has_must_haves or has_priorities or has_constraints

    return has_constraint


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
    current_requirements = state.get("user_requirements") or {}

    try:
        llm_service = get_llm_service()

        # Build context about current requirements
        requirements_context = ""
        if current_requirements:
            requirements_context = f"\n\nCurrent requirements gathered:\n{yaml.dump(current_requirements, default_flow_style=False)}"

        # Generate response
        llm_response = await llm_service.generate(
            messages,
            system_prompt=INTAKE_SYSTEM_PROMPT + requirements_context,
        )

        content = llm_response.content
        content_lower = content.lower()

        # Parse requirements from response and user messages
        last_user_message = ""
        if messages:
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "human":
                    last_user_message = msg.content
                    break

        # Update requirements based on conversation
        updated_requirements = parse_requirements(content, current_requirements)
        updated_requirements = parse_requirements(last_user_message, updated_requirements)

        # Check if user explicitly requested to search
        user_wants_to_search = any(
            phrase in content_lower or phrase in last_user_message.lower()
            for phrase in [
                "let's search",
                "ready to search",
                "start searching",
                "search now",
                "find products",
                "show me",
                "let me see",
            ]
        )

        # Determine if requirements are ready
        requirements_ready = requirements_are_complete(updated_requirements) and (
            user_wants_to_search
            or "let me find" in content_lower
            or "i'll search" in content_lower
        )

        # Determine next phase
        if requirements_ready:
            next_phase = "research"
            goto = "research"
            logger.info(f"Requirements ready: {updated_requirements}")
            logger.info("Transitioning to RESEARCH")
        else:
            next_phase = "intake"
            goto = "__end__"  # Return control to user for next input
            logger.info(f"Requirements incomplete: {updated_requirements}")
            logger.info("Staying in INTAKE")

        return Command(
            update={
                "messages": [AIMessage(content=content)],
                "current_node": "intake",
                "current_phase": next_phase,
                "user_requirements": updated_requirements,
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
