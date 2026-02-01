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


async def intake_node(state: AgentState) -> Command:
    """
    INTAKE node - Gather user requirements through multi-turn conversation.

    This node engages in dialogue to understand what the user wants to buy.
    It uses LLM structured output to extract requirements and LLM judgment
    to determine when enough information has been gathered to proceed to RESEARCH.

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
            # Ready to search - confirm and transition
            confirmation_prompt = """The user has provided enough information. Generate a friendly confirmation message that:
1. Briefly summarizes what they're looking for
2. Confirms you'll search for products
3. Is conversational and encouraging (not robotic)

Keep it to 2-3 sentences."""

            confirmation_messages = messages.copy()
            confirmation_messages.append(HumanMessage(content=confirmation_prompt))

            llm_response = await llm_service.generate(
                confirmation_messages,
                system_prompt=INTAKE_SYSTEM_PROMPT,
            )

            next_phase = "research"
            goto = "research"
            logger.info("Transitioning to RESEARCH")
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

            llm_response = type("Response", (), {"content": response_content})()
            next_phase = "intake"
            goto = "__end__"  # Return control to user for next input
            logger.info("Staying in INTAKE")

        return Command(
            update={
                "messages": [AIMessage(content=llm_response.content)],
                "current_node": "intake",
                "current_phase": next_phase,
                "user_requirements": updated_requirements,
            },
            goto=goto,
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
