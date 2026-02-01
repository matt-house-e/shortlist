"""HITL (Human-in-the-Loop) action handling for chat interface."""

import chainlit as cl

from app.agents.workflow import WorkflowResult, process_message_with_state
from app.chat.citations import format_response_with_citations
from app.chat.table_rendering import send_product_table
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def render_action_buttons(
    result: WorkflowResult, message_content: str, agent_name: str
) -> None:
    """
    Render action buttons if the workflow result has action choices.

    Args:
        result: WorkflowResult containing potential HITL state
        message_content: The message content to display with buttons
        agent_name: The display name of the agent sending the message
    """
    action_choices = result.action_choices
    if not action_choices:
        return

    # Determine checkpoint type from HITL flags
    checkpoint = None
    if result.awaiting_requirements_confirmation:
        checkpoint = "requirements"
    elif result.awaiting_fields_confirmation:
        checkpoint = "fields"
    elif result.awaiting_intent_confirmation:
        checkpoint = "intent"

    if not checkpoint:
        return

    # Create action buttons
    actions = [
        cl.Action(
            name="hitl_action",
            label=choice,
            payload={"checkpoint": checkpoint, "choice": choice},
        )
        for choice in action_choices
    ]

    # Store current actions for cleanup
    cl.user_session.set("current_actions", actions)

    # Send message with action buttons
    await cl.Message(content=message_content, actions=actions, author=agent_name).send()


async def remove_current_actions() -> None:
    """Remove any currently displayed action buttons."""
    current_actions = cl.user_session.get("current_actions", [])
    for action in current_actions:
        await action.remove()
    cl.user_session.set("current_actions", [])


@cl.action_callback("hitl_action")
async def on_hitl_action(action: cl.Action):
    """Handle all HITL button clicks."""
    from app.chat.handlers import (
        emit_phase_transition_toast,
        get_agent_name,
        update_thread_name_from_product,
    )

    logger.info(f"HITL action clicked: {action.payload}")

    # Remove current action buttons
    await remove_current_actions()

    # Get workflow from session
    workflow = cl.user_session.get("workflow")
    if not workflow:
        await cl.Message(content="Session error. Please refresh the page.").send()
        return

    # Get user context
    user = cl.user_session.get("user")
    user_id = user.identifier if user else "anonymous"
    session_id = cl.user_session.get("id", "unknown")

    # Build synthetic HITL message
    checkpoint = action.payload.get("checkpoint")
    choice = action.payload.get("choice")
    synthetic_message = f"[HITL:{checkpoint}:{choice}]"

    logger.info(f"Processing HITL synthetic message: {synthetic_message}")

    # Get product name from state for dynamic step names
    product_name = "product"
    config = {"configurable": {"thread_id": session_id}}
    try:
        current_state = await workflow.aget_state(config)
        if current_state.values:
            requirements = current_state.values.get("user_requirements") or {}
            product_name = requirements.get("product_type") or "product"
    except Exception as e:
        logger.warning(f"Failed to retrieve state for product name: {e}")

    # Process through workflow with loading indicator (only for slow operations)
    if checkpoint == "requirements":
        step_name = f"Searching for {product_name}s..."
        async with cl.Step(name=step_name, type="tool", show_input=False):
            result = await process_message_with_state(
                workflow=workflow,
                message=synthetic_message,
                user_id=user_id,
                session_id=session_id,
            )
    elif checkpoint == "fields":
        step_name = f"Analysing {product_name} specs..."
        async with cl.Step(name=step_name, type="tool", show_input=False):
            result = await process_message_with_state(
                workflow=workflow,
                message=synthetic_message,
                user_id=user_id,
                session_id=session_id,
            )
    else:
        result = await process_message_with_state(
            workflow=workflow,
            message=synthetic_message,
            user_id=user_id,
            session_id=session_id,
        )

    # Handle phase transition toast
    previous_phase = cl.user_session.get("previous_phase", "intake")
    current_phase = result.current_phase
    await emit_phase_transition_toast(previous_phase, current_phase)
    cl.user_session.set("previous_phase", current_phase)

    # Update thread name when transitioning from intake to research
    if previous_phase == "intake" and current_phase == "research":
        await update_thread_name_from_product(product_name)

    # Get agent name for the current phase
    agent_name = get_agent_name(current_phase)

    # Format response with citations if available
    response_content = format_response_with_citations(result.content, result.citations)

    # Check if we need to render action buttons
    if result.action_choices:
        await render_action_buttons(result, response_content, agent_name)
    else:
        await cl.Message(content=response_content, author=agent_name).send()

    # Render comparison table when entering ADVISE phase with data
    if current_phase == "advise" and result.living_table:
        llm_service = cl.user_session.get("llm_service")
        # Get user_requirements from workflow state
        user_requirements = None
        try:
            current_state = await workflow.aget_state(config)
            if current_state.values:
                user_requirements = current_state.values.get("user_requirements")
        except Exception as e:
            logger.warning(f"Failed to retrieve user requirements for table: {e}")
        await send_product_table(
            living_table_data=result.living_table,
            user_requirements=user_requirements,
            llm_service=llm_service,
            agent_name=agent_name,
            include_export_button=True,
        )
