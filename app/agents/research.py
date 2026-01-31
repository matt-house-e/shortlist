"""RESEARCH node - Find candidates and build comparison table."""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.models.state import AgentState
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def research_node(state: AgentState) -> Command:
    """
    RESEARCH node - Find product candidates and build comparison table.

    This node runs automatically without user interaction. It contains two sub-steps:
    1. Explorer (conditional) - Find candidates via web search
    2. Enricher (always) - Build comparison table via Lattice

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing to ADVISE
    """
    logger.info("RESEARCH node processing")

    need_new_search = state.get("need_new_search", True)
    candidates = state.get("candidates", [])

    try:
        # Step 1: Explorer (if needed)
        if need_new_search or not candidates:
            logger.info("Running Explorer sub-step")
            # TODO: Implement Explorer logic (Issue #7)
            # For now, use placeholder
            candidates = [
                {"name": "Product A", "manufacturer": "Brand A", "official_url": "https://example.com/a"},
                {"name": "Product B", "manufacturer": "Brand B", "official_url": "https://example.com/b"},
            ]

        # Step 2: Enricher (always)
        logger.info("Running Enricher sub-step")
        # TODO: Implement Enricher logic (Issue #9)
        # For now, use placeholder comparison table
        comparison_table = {
            "columns": ["Name", "Price", "Rating"],
            "rows": [
                {"name": "Product A", "price": "$50", "rating": "4.5"},
                {"name": "Product B", "price": "$45", "rating": "4.2"},
            ],
        }

        logger.info("RESEARCH complete, transitioning to ADVISE")

        return Command(
            update={
                "current_node": "research",
                "current_phase": "advise",
                "candidates": candidates,
                "comparison_table": comparison_table,
                "need_new_search": False,
                "messages": [AIMessage(content="Research complete. Found products to compare.")],
            },
            goto="advise",
        )

    except Exception as e:
        logger.error(f"RESEARCH error: {e}")
        return Command(
            update={
                "current_node": "research",
                "phase": "error",
                "messages": [AIMessage(content=f"Research failed: {str(e)}")],
            },
            goto="advise",  # Still proceed to ADVISE with error context
        )
