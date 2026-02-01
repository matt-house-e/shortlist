"""Chainlit event handlers - Main entry point for the chat interface."""

import uuid
from datetime import datetime

import chainlit as cl
from chainlit.data.chainlit_data_layer import ChainlitDataLayer

from app.agents.workflow import (
    WorkflowResult,
    create_workflow,
    process_message_with_state,
)
from app.auth.password_auth import password_auth_callback
from app.config import get_settings
from app.models.schemas.shortlist import ComparisonTable
from app.services.llm import LLMService
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


# =============================================================================
# Citation Formatting
# =============================================================================


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


def format_response_with_citations(content: str, citations: list[dict]) -> str:
    """
    Append a Sources section to the response with clickable citation links.

    Args:
        content: The response text
        citations: List of citation dicts with url, title, start_index, end_index

    Returns:
        Response with appended sources section
    """
    if not citations:
        return content

    # Deduplicate citations by URL
    seen_urls = set()
    unique_citations = []
    for cite in citations:
        if cite["url"] not in seen_urls:
            seen_urls.add(cite["url"])
            unique_citations.append(cite)

    # Build sources section
    sources = "\n\n---\n**Sources:**\n"
    for cite in unique_citations:
        title = cite.get("title", cite["url"])
        sources += f"- [{title}]({cite['url']})\n"

    return content + sources


# =============================================================================
# Table Rendering and Export
# =============================================================================


def render_table_markdown(living_table_data: dict | None, max_rows: int = 10) -> str | None:
    """
    Render the living table as markdown for display in chat.

    Args:
        living_table_data: Serialized ComparisonTable dict
        max_rows: Maximum number of rows to display

    Returns:
        Markdown table string, or None if no table data
    """
    if not living_table_data:
        return None

    try:
        table = ComparisonTable.model_validate(living_table_data)
        if not table.rows:
            return None

        return table.to_markdown(max_rows=max_rows, show_pending=True)
    except Exception as e:
        logger.warning(f"Failed to render table: {e}")
        return None


async def send_table_with_export(
    living_table_data: dict | None,
    agent_name: str,
    include_export_button: bool = True,
) -> None:
    """
    Send the comparison table as a message with an optional export button.

    Args:
        living_table_data: Serialized ComparisonTable dict
        agent_name: The display name of the agent
        include_export_button: Whether to include an "Export CSV" button
    """
    if not living_table_data:
        return

    table_markdown = render_table_markdown(living_table_data)
    if not table_markdown:
        return

    # Build message with table
    message_content = f"## Comparison Table\n\n{table_markdown}"

    if include_export_button:
        # Create export action button
        export_action = cl.Action(
            name="export_csv",
            label="Export CSV",
            payload={"action": "export_csv"},
        )
        await cl.Message(
            content=message_content,
            actions=[export_action],
            author=agent_name,
        ).send()
    else:
        await cl.Message(content=message_content, author=agent_name).send()


@cl.action_callback("export_csv")
async def on_export_csv(action: cl.Action):
    """Handle CSV export button click."""
    logger.info("Export CSV action clicked")

    # Get living table from session state
    workflow = cl.user_session.get("workflow")
    if not workflow:
        await cl.Message(content="Session error. Please refresh the page.").send()
        return

    # Get the current state from the workflow
    session_id = cl.user_session.get("id", "unknown")
    config = {"configurable": {"thread_id": session_id}}

    try:
        current_state = await workflow.aget_state(config)
        living_table_data = (
            current_state.values.get("living_table") if current_state.values else None
        )

        if not living_table_data:
            await cl.Message(
                content="No comparison table available to export.",
                author="System",
            ).send()
            return

        # Convert to ComparisonTable and export
        table = ComparisonTable.model_validate(living_table_data)
        csv_content = table.to_csv(exclude_internal=True)

        if not csv_content:
            await cl.Message(
                content="The comparison table is empty.",
                author="System",
            ).send()
            return

        # Create CSV file element
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comparison_table_{timestamp}.csv"

        # Send as file attachment
        elements = [
            cl.File(
                name=filename,
                content=csv_content.encode("utf-8"),
                display="inline",
            )
        ]

        await cl.Message(
            content=f"Here's your comparison table export ({table.get_row_count()} products):",
            elements=elements,
            author="System",
        ).send()

    except Exception as e:
        logger.exception(f"Failed to export CSV: {e}")
        await cl.Message(
            content="Failed to export the comparison table. Please try again.",
            author="System",
        ).send()


# =============================================================================
# Data Layer
# =============================================================================


@cl.data_layer
def get_data_layer():
    """
    Create Chainlit data layer for conversation persistence.

    Strips SQLAlchemy driver prefix from DATABASE_URL for asyncpg compatibility.
    """
    # Convert SQLAlchemy URL to plain postgres URL for Chainlit
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return ChainlitDataLayer(database_url=db_url)


# =============================================================================
# Authentication
# =============================================================================


@cl.password_auth_callback
async def auth_callback(username: str, password: str) -> cl.User | None:
    """Handle password authentication."""
    return await password_auth_callback(username, password)


# =============================================================================
# Starters (ChatGPT-style welcome page)
# =============================================================================

STARTER_DIRECT_RESPONSES = {
    "Help me find a product to buy": "Great! What type of product are you looking for?",
    "I want to compare different options for something I'm buying": "I can help you compare options. What product category are you researching?",
    "I have a budget and need recommendations": "Happy to help you find options within your budget. What are you shopping for, and what's your budget range?",
    "I need help deciding what to buy": "I'll help you make a decision. What kind of product are you considering?",
}


@cl.set_starters
async def set_starters():
    """Define starter prompts for the welcome screen."""
    return [
        cl.Starter(label="Find a Product", message="Help me find a product to buy"),
        cl.Starter(
            label="Compare Options",
            message="I want to compare different options for something I'm buying",
        ),
        cl.Starter(label="Budget Shopping", message="I have a budget and need recommendations"),
        cl.Starter(label="Quick Research", message="I need help deciding what to buy"),
    ]


# =============================================================================
# Chat Lifecycle
# =============================================================================


@cl.on_chat_start
async def on_chat_start():
    """Initialize a new chat session."""
    logger.info("Starting new chat session")

    # Initialize services
    llm_service = LLMService(settings)

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


@cl.action_callback("hitl_action")
async def on_hitl_action(action: cl.Action):
    """Handle all HITL button clicks."""
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

    # Process through workflow
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
        await send_table_with_export(
            result.living_table,
            agent_name,
            include_export_button=True,
        )


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
        await send_table_with_export(
            result.living_table,
            agent_name,
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
