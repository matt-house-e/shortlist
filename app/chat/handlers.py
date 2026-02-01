"""Chainlit event handlers - Main entry point for the chat interface."""

import uuid

import chainlit as cl
from chainlit.data import get_data_layer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer

from app.agents.workflow import (
    create_workflow,
    process_message_with_state,
)
from app.auth.password_auth import password_auth_callback
from app.chat.citations import format_response_with_citations
from app.chat.hitl_actions import remove_current_actions, render_action_buttons
from app.chat.starters import STARTER_DIRECT_RESPONSES
from app.chat.table_rendering import send_product_table
from app.config import get_settings
from app.services.llm import get_llm_service
from app.utils.logger import get_logger, setup_logging
from app.utils.sanitization import sanitize_input

# Initialize logging before creating any loggers
settings = get_settings()
setup_logging(level=settings.log_level)

logger = get_logger(__name__)


# =============================================================================
# Agent Display Names
# =============================================================================

PHASE_TO_AGENT_NAME = {
    "intake": "Intake Agent",
    "research": "Research Agent",
    "advise": "Advisor Agent",
}

# Toast messages for phase transitions
PHASE_TRANSITION_TOASTS = {
    ("intake", "research"): {
        "title": "Moving to Research",
        "description": "Searching for products...",
    },
    ("research", "advise"): {
        "title": "Analysis Complete",
        "description": "Ready to present recommendations",
    },
    ("advise", "intake"): {
        "title": "Refining Requirements",
        "description": "Let's update your criteria",
    },
    ("advise", "research"): {
        "title": "Finding More Options",
        "description": "Searching for additional products...",
    },
}


def get_agent_name(phase: str) -> str:
    """Get the display name for an agent based on the current phase."""
    return PHASE_TO_AGENT_NAME.get(phase, "Assistant")


async def emit_phase_transition_toast(previous_phase: str, current_phase: str) -> None:
    """Emit a toast notification when the phase changes."""
    if previous_phase == current_phase:
        return

    toast_config = PHASE_TRANSITION_TOASTS.get((previous_phase, current_phase))
    if toast_config:
        await cl.context.emitter.emit(
            "ui:toast",
            {
                "title": toast_config["title"],
                "description": toast_config["description"],
                "type": "info",
            },
        )
        logger.info(f"Phase transition toast: {previous_phase} -> {current_phase}")


async def update_thread_name_from_product(product_type: str | None) -> None:
    """
    Update the chat thread name to the product being researched.

    Args:
        product_type: The product type from user requirements (e.g., "electric kettle")
    """
    if not product_type:
        return

    # Check if we've already set the thread name this session
    if cl.user_session.get("thread_name_set"):
        return

    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        return

    data_layer = get_data_layer()
    if not data_layer:
        return

    try:
        # Capitalize for display (e.g., "electric kettle" -> "Electric Kettle")
        thread_name = product_type.title()
        await data_layer.update_thread(thread_id=thread_id, name=thread_name)
        cl.user_session.set("thread_name_set", True)
        logger.info(f"Updated thread name to: {thread_name}")
    except Exception as e:
        logger.warning(f"Failed to update thread name: {e}")


# =============================================================================
# Data Layer (optional - requires PostgreSQL)
# =============================================================================

if settings.enable_data_layer:

    @cl.data_layer
    def get_data_layer():
        """
        Create Chainlit data layer for conversation persistence.

        Strips SQLAlchemy driver prefix for asyncpg compatibility.
        """
        # Convert SQLAlchemy URL to plain postgres URL for Chainlit
        db_url = settings.app_database_url.replace("postgresql+asyncpg://", "postgresql://")
        return ChainlitDataLayer(database_url=db_url)


# =============================================================================
# Authentication
# =============================================================================


@cl.password_auth_callback
async def auth_callback(username: str, password: str) -> cl.User | None:
    """Handle password authentication."""
    return await password_auth_callback(username, password)


# =============================================================================
# Chat Lifecycle
# =============================================================================


@cl.on_chat_start
async def on_chat_start():
    """Initialize a new chat session."""
    logger.info("Starting new chat session")

    # Initialize services
    llm_service = get_llm_service()

    # Create workflow graph
    workflow = create_workflow(llm_service)

    # Generate workflow ID and get thread ID
    workflow_id = str(uuid.uuid4())
    thread_id = cl.context.session.thread_id if cl.context.session else ""

    # Store in session
    cl.user_session.set("workflow", workflow)
    cl.user_session.set("llm_service", llm_service)
    cl.user_session.set("workflow_id", workflow_id)
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("previous_phase", "intake")  # Track phase for toast notifications

    logger.info(f"Session initialized: workflow_id={workflow_id}, thread_id={thread_id}")


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages."""
    logger.info(f"Received message: {message.content[:100]}...")

    # Remove any existing action buttons (non-blocking pattern)
    await remove_current_actions()

    # Handle starter direct responses (skip LLM for faster feedback)
    if message.content in STARTER_DIRECT_RESPONSES:
        await cl.Message(
            content=STARTER_DIRECT_RESPONSES[message.content], author="Assistant"
        ).send()
        return

    # Sanitize user input
    sanitized_content = sanitize_input(message.content)
    if not sanitized_content:
        await cl.Message(content="Please enter a valid message.").send()
        return

    # Get workflow from session
    workflow = cl.user_session.get("workflow")
    if not workflow:
        await cl.Message(content="Session error. Please refresh the page.").send()
        return

    # Get user context
    user = cl.user_session.get("user")
    user_id = user.identifier if user else "anonymous"
    session_id = cl.user_session.get("id", "unknown")

    # Process through workflow
    result = await process_message_with_state(
        workflow=workflow,
        message=sanitized_content,
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
        config = {"configurable": {"thread_id": session_id}}
        try:
            current_state = await workflow.aget_state(config)
            if current_state.values:
                requirements = current_state.values.get("user_requirements") or {}
                product_type = requirements.get("product_type")
                await update_thread_name_from_product(product_type)
        except Exception as e:
            logger.warning(f"Failed to get product type for thread name: {e}")

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
        config = {"configurable": {"thread_id": session_id}}
        try:
            current_state = await workflow.aget_state(config)
            if current_state.values:
                user_requirements = current_state.values.get("user_requirements")
        except Exception as e:
            logger.warning(f"Failed to retrieve user requirements for export: {e}")
        await send_product_table(
            living_table_data=result.living_table,
            user_requirements=user_requirements,
            llm_service=llm_service,
            agent_name=agent_name,
            include_export_button=True,
        )


@cl.on_chat_end
async def on_chat_end():
    """Clean up when chat session ends."""
    logger.info("Chat session ended")


# =============================================================================
# Chat Settings (Optional)
# =============================================================================


@cl.on_settings_update
async def on_settings_update(settings: dict):
    """Handle user settings updates."""
    logger.info(f"Settings updated: {settings}")
    cl.user_session.set("user_settings", settings)


# =============================================================================
# Import submodules to register their decorators
# =============================================================================
# These imports must be at the bottom to avoid circular imports while
# ensuring Chainlit discovers the decorated handlers

import app.chat.hitl_actions  # noqa: E402, F401
import app.chat.starters  # noqa: E402, F401
import app.chat.table_rendering  # noqa: E402, F401
