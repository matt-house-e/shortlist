"""RESEARCH node - Find candidates and build comparison table."""

from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.agents.research_enricher import enrich_living_table, enricher_step
from app.agents.research_explorer import explorer_step, generate_field_definitions
from app.agents.research_table import (
    add_candidates_to_table,
    add_requested_fields_to_table,
    build_field_definitions_list,
    get_or_create_living_table,
)
from app.config.settings import get_settings
from app.models.schemas.shortlist import CellStatus, FieldDefinition
from app.models.state import AgentState
from app.services.llm import LLMService
from app.utils.hitl import clear_hitl_flags, parse_hitl_choice
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _format_field_name(name: str) -> str:
    """Convert field_name_like_this to 'Field Name Like This'."""
    return name.replace("_", " ").title()


def _format_fields_for_display(field_definitions: list[dict]) -> str:
    """
    Format field definitions for user display in HITL confirmation.

    Args:
        field_definitions: List of field definition dicts

    Returns:
        Formatted string for display with rich markdown
    """
    # Group by category
    basics = []  # standard fields like name, price, official_url
    specs = []  # category-specific technical specs
    priorities = []  # user-driven based on their requirements

    for field in field_definitions:
        name = field.get("name", "unknown")
        cat = field.get("category", "standard")

        # Skip qualification fields (internal)
        if cat == "qualification":
            continue

        display_name = _format_field_name(name)

        if cat == "standard":
            basics.append(display_name)
        elif cat == "category":
            specs.append(display_name)
        else:
            priorities.append(display_name)

    lines = []

    if basics:
        lines.append("**Basics:** " + ", ".join(basics))

    if specs:
        # Format specs as a bullet list for readability
        lines.append("\n**Specs I'll research:**")
        for spec in specs:
            lines.append(f"- {spec}")

    if priorities:
        lines.append("\n**Based on your priorities:**")
        for priority in priorities:
            lines.append(f"- {priority}")

    return "\n".join(lines) if lines else "Standard comparison fields"


async def research_node(state: AgentState) -> Command:
    """
    RESEARCH node - Find product candidates and build comparison table.

    This node supports three data flow paths:
    1. New Search (need_new_search=True): Run explorer, add rows to living table, enrich all
    2. Add Fields (requested_fields set): Add new fields to existing table, enrich only new column
    3. Re-enrich (need_new_search=False, no requested_fields): Re-enrich flagged cells

    HITL Flow:
    - After Explorer finds candidates, shows "Enrich Now" / "Modify Fields" buttons
    - User must confirm before proceeding to expensive Lattice enrichment

    Args:
        state: Current workflow state

    Returns:
        Command with state updates and routing
    """
    logger.info("RESEARCH node processing")

    messages = state.get("messages", [])
    need_new_search = state.get("need_new_search", True)
    candidates = state.get("candidates", [])
    awaiting_fields = state.get("awaiting_fields_confirmation", False)

    # FIX: Read requested_fields from state (this was the bug - never read before!)
    requested_fields = state.get("requested_fields", [])
    if requested_fields:
        logger.info(f"RESEARCH: Detected requested_fields from ADVISE: {requested_fields}")

    # Check for HITL action at start
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content") and last_message.content.startswith("[HITL:fields:"):
            choice = parse_hitl_choice(last_message.content)
            logger.info(f"RESEARCH: HITL action received - {choice}")

            if choice == "Enrich Now":
                # User confirmed, proceed to enrichment
                logger.info("RESEARCH: User confirmed fields, running Enricher")

                # Get pending field definitions from state
                pending_fields = state.get("pending_field_definitions", [])
                existing_candidates = state.get("candidates", [])

                if not pending_fields or not existing_candidates:
                    logger.error("RESEARCH: Missing pending data for enrichment")
                    return Command(
                        update={
                            "messages": [
                                AIMessage(
                                    content="Something went wrong. Let me restart the search."
                                )
                            ],
                            "current_node": "research",
                            "current_phase": "research",
                            **clear_hitl_flags(),
                        },
                        goto="research",
                    )

                try:
                    # Build living table and enrich
                    living_table = get_or_create_living_table(state)

                    # Add standard fields to table if empty
                    if not living_table.fields:
                        for field_dict in pending_fields:
                            field_def = FieldDefinition(
                                name=field_dict["name"],
                                prompt=field_dict["prompt"],
                                data_type=field_dict["data_type"],
                                category=field_dict["category"],
                            )
                            living_table.add_field(field_def)

                    # Add candidates to table (with deduplication)
                    add_candidates_to_table(living_table, existing_candidates)

                    # Enrich all pending cells
                    living_table = await enrich_living_table(living_table)

                    # Also create legacy comparison_table for backward compatibility
                    comparison_table = await enricher_step(existing_candidates, pending_fields)

                    num_candidates = living_table.get_row_count()
                    qualified = len(living_table.get_qualified_rows())
                    response_msg = (
                        f"Research complete! I found {qualified} products that match your requirements "
                        f"(out of {num_candidates} analyzed)."
                    )

                    logger.info("RESEARCH: Enrichment complete, transitioning to ADVISE")

                    return Command(
                        update={
                            "current_node": "research",
                            "current_phase": "advise",
                            "living_table": living_table.model_dump(),
                            "comparison_table": comparison_table,  # Legacy support
                            "need_new_search": False,
                            "requested_fields": [],  # Clear after processing
                            "advise_has_presented": False,
                            "messages": [AIMessage(content=response_msg)],
                            **clear_hitl_flags(),
                        },
                        goto="advise",
                    )
                except Exception:
                    logger.exception("RESEARCH enrichment error")
                    return Command(
                        update={
                            "messages": [
                                AIMessage(content="I encountered an issue during enrichment.")
                            ],
                            "current_node": "research",
                            "current_phase": "error",
                            **clear_hitl_flags(),
                        },
                        goto="advise",
                    )
            else:
                # User wants to modify fields
                logger.info("RESEARCH: User wants to modify fields")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content="What fields would you like me to add or change for the comparison? For example, you could ask for 'energy efficiency', 'warranty length', or 'weight'."
                            )
                        ],
                        "current_node": "research",
                        "current_phase": "research",
                        **clear_hitl_flags(),
                    },
                    goto="__end__",
                )

    # Check if we're awaiting confirmation (came back with non-HITL message)
    if awaiting_fields and messages:
        # User typed something instead of clicking button - treat as field modification request
        last_message = messages[-1]
        if hasattr(last_message, "content") and not last_message.content.startswith("[HITL:"):
            logger.info("RESEARCH: User provided text while awaiting fields confirmation")
            pending_fields = state.get("pending_field_definitions", [])
            existing_candidates = state.get("candidates", [])

            if pending_fields and existing_candidates:
                try:
                    # Build living table and enrich
                    living_table = get_or_create_living_table(state)

                    if not living_table.fields:
                        for field_dict in pending_fields:
                            field_def = FieldDefinition(
                                name=field_dict["name"],
                                prompt=field_dict["prompt"],
                                data_type=field_dict["data_type"],
                                category=field_dict["category"],
                            )
                            living_table.add_field(field_def)

                    add_candidates_to_table(living_table, existing_candidates)
                    living_table = await enrich_living_table(living_table)

                    comparison_table = await enricher_step(existing_candidates, pending_fields)
                    num_candidates = living_table.get_row_count()
                    response_msg = (
                        f"Research complete! I found {num_candidates} products to compare."
                    )

                    return Command(
                        update={
                            "current_node": "research",
                            "current_phase": "advise",
                            "living_table": living_table.model_dump(),
                            "comparison_table": comparison_table,
                            "need_new_search": False,
                            "requested_fields": [],
                            "advise_has_presented": False,
                            "messages": [AIMessage(content=response_msg)],
                            **clear_hitl_flags(),
                        },
                        goto="advise",
                    )
                except Exception:
                    logger.exception("RESEARCH enrichment error")

    try:
        # =====================================================================
        # PATH 2: Add Fields Only (requested_fields set, need_new_search=False)
        # This is the FIX for the bug where requested_fields was never read!
        # =====================================================================
        if requested_fields and not need_new_search:
            logger.info(f"RESEARCH: Adding requested fields: {requested_fields}")

            # Get existing living table
            living_table = get_or_create_living_table(state)

            if not living_table.rows:
                logger.warning("No existing rows in table, cannot add fields without data")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content="I need to find products first before I can add comparison fields. Let me search for options."
                            )
                        ],
                        "current_node": "research",
                        "current_phase": "research",
                        "need_new_search": True,
                        "requested_fields": [],
                        **clear_hitl_flags(),
                    },
                    goto="research",
                )

            # Add the requested fields to the table (marks all rows PENDING for these fields)
            added_fields = add_requested_fields_to_table(living_table, requested_fields)

            if not added_fields:
                logger.info("All requested fields already exist")
                return Command(
                    update={
                        "messages": [
                            AIMessage(
                                content=f"The fields {', '.join(requested_fields)} are already in the comparison table."
                            )
                        ],
                        "current_node": "research",
                        "current_phase": "advise",
                        "requested_fields": [],
                        **clear_hitl_flags(),
                    },
                    goto="advise",
                )

            # Enrich only the new fields (cells are PENDING only for new fields)
            logger.info(
                f"Enriching {len(added_fields)} new fields for {living_table.get_row_count()} products"
            )
            living_table = await enrich_living_table(living_table)

            # Build legacy comparison table for backward compatibility
            field_defs_list = build_field_definitions_list(living_table)
            comparison_table_data = state.get("comparison_table") or {}
            existing_candidates_data = comparison_table_data.get("candidates", [])

            # Merge new field data into existing comparison_table candidates
            for candidate_data in existing_candidates_data:
                candidate_name = candidate_data.get("name", "")
                # Find matching row in living table
                for row in living_table.rows.values():
                    if row.candidate.name == candidate_name:
                        for field_name in added_fields:
                            cell = row.cells.get(field_name)
                            if cell and cell.status == CellStatus.ENRICHED:
                                candidate_data[field_name] = cell.value
                        break

            comparison_table = {
                "fields": field_defs_list,
                "candidates": existing_candidates_data,
            }

            response_msg = (
                f"I've added {', '.join(added_fields)} to the comparison table and enriched "
                f"the data for all {living_table.get_row_count()} products."
            )

            logger.info("RESEARCH: Field addition complete, returning to ADVISE")

            return Command(
                update={
                    "current_node": "research",
                    "current_phase": "advise",
                    "living_table": living_table.model_dump(),
                    "comparison_table": comparison_table,
                    "need_new_search": False,
                    "requested_fields": [],  # Clear after processing
                    "advise_has_presented": False,
                    "messages": [AIMessage(content=response_msg)],
                    **clear_hitl_flags(),
                },
                goto="advise",
            )

        # =====================================================================
        # PATH 1: New Search (need_new_search=True or no candidates)
        # =====================================================================
        if need_new_search or not candidates:
            logger.info("Running Explorer sub-step")
            candidates, field_definitions = await explorer_step(state)

            # After Explorer completes, pause for HITL confirmation
            fields_summary = _format_fields_for_display(field_definitions)
            confirmation_message = (
                f"🔍 **Found {len(candidates)} products!**\n\n{fields_summary}\n\nReady to analyze?"
            )

            logger.info("RESEARCH: Explorer complete, awaiting HITL confirmation for fields")

            return Command(
                update={
                    "messages": [AIMessage(content=confirmation_message)],
                    "current_node": "research",
                    "current_phase": "research",
                    "candidates": candidates,
                    "pending_field_definitions": field_definitions,
                    "awaiting_fields_confirmation": True,
                    "action_choices": ["Enrich Now", "Modify Fields"],
                },
                goto="__end__",  # Return control to user for HITL
            )

        # =====================================================================
        # PATH 3: Re-enrich (need_new_search=False, no requested_fields)
        # =====================================================================
        logger.info("Skipping Explorer (re-enrichment mode)")

        # Get existing living table or build from legacy data
        living_table = get_or_create_living_table(state)

        # If living table is empty, build from legacy comparison_table
        if not living_table.rows:
            comparison_table_data = state.get("comparison_table") or {}
            field_definitions = comparison_table_data.get("fields", [])

            if not field_definitions:
                logger.warning("No existing field definitions found, regenerating")
                requirements = state.get("user_requirements", {})
                product_type = requirements.get("product_type", "product")
                settings = get_settings()
                llm_service = LLMService(settings)
                field_definitions = await generate_field_definitions(
                    product_type, requirements, llm_service
                )

            # Add fields to living table
            for field_dict in field_definitions:
                field_def = FieldDefinition(
                    name=field_dict["name"],
                    prompt=field_dict["prompt"],
                    data_type=field_dict["data_type"],
                    category=field_dict["category"],
                )
                living_table.add_field(field_def)

            # Add candidates to living table
            add_candidates_to_table(living_table, candidates)

        # Enrich pending cells
        living_table = await enrich_living_table(living_table)

        # Also run legacy enricher for backward compatibility
        field_defs_list = build_field_definitions_list(living_table)
        comparison_table = await enricher_step(candidates, field_defs_list)

        num_candidates = living_table.get_row_count()
        response_msg = f"Research complete! I found {num_candidates} products to compare."

        logger.info("RESEARCH complete, transitioning to ADVISE")

        return Command(
            update={
                "current_node": "research",
                "current_phase": "advise",
                "candidates": candidates,
                "living_table": living_table.model_dump(),
                "comparison_table": comparison_table,
                "need_new_search": False,
                "requested_fields": [],
                "advise_has_presented": False,
                "messages": [AIMessage(content=response_msg)],
                **clear_hitl_flags(),
            },
            goto="advise",
        )

    except Exception:
        logger.exception("RESEARCH error")
        error_msg = "I encountered an issue during research. Let me still show you what I found."
        return Command(
            update={
                "current_node": "research",
                "current_phase": "error",
                "messages": [AIMessage(content=error_msg)],
                **clear_hitl_flags(),
            },
            goto="advise",  # Still proceed to ADVISE with error context
        )
