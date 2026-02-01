"""Chainlit event handlers - Main entry point for the chat interface."""

import uuid

import chainlit as cl
from chainlit.data.chainlit_data_layer import ChainlitDataLayer

from app.agents.workflow import create_workflow, process_message_with_state
from app.auth.password_auth import password_auth_callback
from app.config import get_settings
from app.services.llm import LLMService
from app.utils.logger import get_logger, setup_logging
from app.utils.sanitization import sanitize_input

# Initialize logging before creating any loggers
settings = get_settings()
setup_logging(level=settings.log_level)

logger = get_logger(__name__)


# =============================================================================
# Citation Formatting
# =============================================================================


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

    logger.info(f"Session initialized: workflow_id={workflow_id}, thread_id={thread_id}")

    # Send welcome message (optional)
    await cl.Message(
        content="Hello! How can I assist you today?",
        author="Assistant",
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages."""
    logger.info(f"Received message: {message.content[:100]}...")

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

    # Create status indicator
    async with cl.Step(name="Processing", type="run") as step:
        step.input = sanitized_content

        # Process through workflow
        result = await process_message_with_state(
            workflow=workflow,
            message=sanitized_content,
            user_id=user_id,
            session_id=session_id,
        )

        step.output = result.content

    # Format response with citations if available
    response_content = format_response_with_citations(result.content, result.citations)

    # Send response
    await cl.Message(content=response_content, author="Assistant").send()


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
