"""Table rendering and export functionality for chat interface."""

from datetime import datetime

import chainlit as cl

from app.models.schemas.shortlist import ComparisonTable
from app.services.llm import LLMService
from app.services.table_rendering import prepare_product_table_props
from app.utils.logger import get_logger

logger = get_logger(__name__)


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


async def send_product_table(
    living_table_data: dict | None,
    user_requirements: dict | None,
    llm_service: LLMService,
    agent_name: str,
    include_export_button: bool = True,
) -> bool:
    """
    Send the comparison table as a custom React element.

    Uses the ProductTable component for a compact, interactive display with:
    - Top 10 products (qualified first, then by enrichment completeness)
    - 5-7 LLM-selected key fields
    - Clickable product name links
    - Status indicators for pending/failed cells

    Args:
        living_table_data: Serialized ComparisonTable dict
        user_requirements: User requirements dict for context
        llm_service: LLM service for field selection
        agent_name: The display name of the agent
        include_export_button: Whether to include an "Export CSV" button

    Returns:
        True if table was sent successfully, False otherwise
    """
    if not living_table_data:
        return False

    try:
        # Prepare props for the React component
        logger.info("Preparing ProductTable props...")
        props = await prepare_product_table_props(
            living_table_data=living_table_data,
            user_requirements=user_requirements,
            llm_service=llm_service,
        )

        if not props:
            # Fall back to markdown table if props preparation fails
            logger.warning("ProductTable props preparation failed, falling back to markdown")
            await send_table_with_export(living_table_data, agent_name, include_export_button)
            return True

        logger.info(f"ProductTable props ready: {len(props.get('products', []))} products")

        # Create custom element
        table_element = cl.CustomElement(
            name="ProductTable",
            props=props,
            display="inline",
        )
        logger.info(f"Created CustomElement: {table_element}")

        # Build message with optional export button
        if include_export_button:
            export_action = cl.Action(
                name="export_csv",
                label="Export CSV",
                payload={"action": "export_csv"},
            )
            await cl.Message(
                content="## Comparison Table",
                elements=[table_element],
                actions=[export_action],
                author=agent_name,
            ).send()
        else:
            await cl.Message(
                content="## Comparison Table",
                elements=[table_element],
                author=agent_name,
            ).send()

        logger.info(
            f"Sent ProductTable: {len(props['products'])} products, {len(props['fields'])} fields"
        )
        return True

    except Exception as e:
        logger.exception(f"Failed to send ProductTable: {e}")
        # Fall back to markdown table
        await send_table_with_export(living_table_data, agent_name, include_export_button)
        return True


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
