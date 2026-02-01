"""RESEARCH node - Find candidates and build comparison table."""

import asyncio
import json
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config.settings import get_settings
from app.models.schemas.shortlist import SearchQuery, SearchQueryPlan
from app.models.state import AgentState
from app.services.lattice import LatticeService
from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"
EXPLORER_PROMPT_PATH = PROMPTS_DIR / "explorer.yaml"

with open(EXPLORER_PROMPT_PATH) as f:
    EXPLORER_PROMPTS = yaml.safe_load(f)

# Query generation prompt for LLM-driven search strategy
QUERY_GENERATION_PROMPT = """You are a product research strategist. Given user requirements,
generate 3-6 diverse web search queries to find matching products.

User Requirements:
{requirements_json}

Generate search queries that:
1. Cover different angles (review sites, Reddit, comparison articles, manufacturer sites)
2. Use different phrasings to catch different results
3. Include time-relevant terms (2025, 2026, latest)
4. Balance specific features vs broader category searches

For extensive requirements, split features across queries rather than cramming all into one.

Return as JSON:
{{
    "queries": [
        {{"query": "best 4-slot toasters under £30 2025 reviews", "angle": "review_sites"}},
        {{"query": "4 slot toaster defrost function reddit recommendations", "angle": "community"}},
        {{"query": "budget toaster stainless steel comparison UK", "angle": "comparison"}}
    ],
    "strategy_notes": "Brief explanation of search strategy"
}}
"""

# System prompt for web search to extract product candidates
SEARCH_SYSTEM_PROMPT = """You are a product researcher. Search for products matching the query.
For each product found, extract:
- Full product name
- Manufacturer/brand
- Official product URL (manufacturer site preferred, not retailer)
- Brief description

Return results as a JSON array:
[
    {{"name": "Product Name", "manufacturer": "Brand", "official_url": "https://...", "description": "Brief description"}},
    ...
]

Focus on finding real, specific products. Include 5-15 products per search."""


def _summarize_requirements(requirements: dict) -> str:
    """
    Create a concise summary of requirements for qualification prompts.

    Args:
        requirements: User requirements dict

    Returns:
        Human-readable requirements summary
    """
    parts = []

    product_type = requirements.get("product_type", "product")
    parts.append(f"Product type: {product_type}")

    budget_min = requirements.get("budget_min")
    budget_max = requirements.get("budget_max")
    if budget_min and budget_max:
        parts.append(f"Budget: ${budget_min}-${budget_max}")
    elif budget_max:
        parts.append(f"Budget: under ${budget_max}")
    elif budget_min:
        parts.append(f"Budget: over ${budget_min}")

    must_haves = requirements.get("must_haves", [])
    if must_haves:
        parts.append(f"Must have: {', '.join(must_haves)}")

    nice_to_haves = requirements.get("nice_to_haves", [])
    if nice_to_haves:
        parts.append(f"Nice to have: {', '.join(nice_to_haves)}")

    priorities = requirements.get("priorities", [])
    if priorities:
        parts.append(f"Priorities: {', '.join(priorities)}")

    constraints = requirements.get("constraints", [])
    if constraints:
        parts.append(f"Constraints: {', '.join(constraints)}")

    return "; ".join(parts)


def _get_fallback_queries(product_type: str, requirements: dict) -> list[SearchQuery]:
    """
    Generate fallback search queries when LLM query generation fails.

    Args:
        product_type: Type of product
        requirements: User requirements dict

    Returns:
        List of default SearchQuery objects
    """
    budget_max = requirements.get("budget_max")
    budget_str = f" under ${budget_max}" if budget_max else ""
    must_haves = requirements.get("must_haves", [])
    features_str = f" {' '.join(must_haves[:2])}" if must_haves else ""

    return [
        SearchQuery(
            query=f"best {product_type}{budget_str} 2025 reviews",
            angle="review_sites",
        ),
        SearchQuery(
            query=f"{product_type}{features_str} recommendations reddit",
            angle="community",
        ),
        SearchQuery(
            query=f"top rated {product_type} comparison 2025",
            angle="comparison",
        ),
    ]


async def _generate_search_queries(
    llm_service: LLMService,
    requirements: dict,
) -> SearchQueryPlan:
    """
    Use LLM to generate diverse search queries based on requirements.

    Args:
        llm_service: LLM service instance
        requirements: User requirements dict

    Returns:
        SearchQueryPlan with 3-6 diverse queries
    """
    product_type = requirements.get("product_type", "product")

    try:
        # Format the prompt with requirements
        prompt = QUERY_GENERATION_PROMPT.format(
            requirements_json=json.dumps(requirements, indent=2)
        )

        # Generate structured output
        result = await llm_service.generate_structured(
            messages=[HumanMessage(content=prompt)],
            schema=SearchQueryPlan,
        )

        logger.info(f"Generated {len(result.queries)} queries: {result.strategy_notes}")
        return result

    except Exception as e:
        logger.warning(f"Query generation failed, using fallback: {e}")
        return SearchQueryPlan(
            queries=_get_fallback_queries(product_type, requirements),
            strategy_notes="Fallback queries due to generation error",
        )


def _extract_candidates_from_response(response_content: str) -> list[dict]:
    """
    Extract product candidates from web search response.

    Args:
        response_content: Raw response content from web search

    Returns:
        List of candidate dicts
    """
    candidates = []

    # Try to extract JSON array from response
    try:
        # Look for JSON array in the response
        content = response_content.strip()

        # Find JSON array bounds
        start_idx = content.find("[")
        end_idx = content.rfind("]")

        if start_idx != -1 and end_idx != -1:
            json_str = content[start_idx : end_idx + 1]
            parsed = json.loads(json_str)

            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "name" in item:
                        candidates.append(
                            {
                                "name": item.get("name", ""),
                                "manufacturer": item.get("manufacturer", "Unknown"),
                                "official_url": item.get("official_url"),
                                "description": item.get("description", ""),
                            }
                        )
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from response: {e}")

    return candidates


def _normalize_name(name: str) -> str:
    """Normalize product name for deduplication comparison."""
    return name.lower().strip().replace("-", " ").replace("_", " ")


def _deduplicate_candidates(candidates: list[dict]) -> list[dict]:
    """
    Deduplicate candidates by fuzzy name matching.

    Args:
        candidates: List of candidate dicts

    Returns:
        Deduplicated list
    """
    seen_names: dict[str, dict] = {}

    for candidate in candidates:
        name = candidate.get("name", "")
        if not name:
            continue

        normalized = _normalize_name(name)

        # Simple deduplication: check for exact normalized match
        # or if one name contains the other
        is_duplicate = False
        for seen_normalized in list(seen_names.keys()):
            if normalized == seen_normalized:
                is_duplicate = True
                break
            # Check if one contains the other (fuzzy match)
            if normalized in seen_normalized or seen_normalized in normalized:
                # Keep the one with more info (longer name usually)
                if len(name) > len(seen_names[seen_normalized].get("name", "")):
                    del seen_names[seen_normalized]
                else:
                    is_duplicate = True
                break

        if not is_duplicate:
            seen_names[normalized] = candidate

    deduped = list(seen_names.values())
    logger.debug(f"Deduplicated {len(candidates)} -> {len(deduped)} candidates")
    return deduped


async def _execute_parallel_searches(
    queries: list[SearchQuery],
    llm_service: LLMService,
    product_type: str,
) -> list[dict]:
    """
    Execute multiple web searches in parallel.

    Args:
        queries: List of search queries
        llm_service: LLM service instance
        product_type: Type of product for context

    Returns:
        List of all candidates from all searches (not yet deduplicated)
    """

    async def single_search(query: SearchQuery) -> list[dict]:
        """Execute a single web search and extract candidates."""
        try:
            logger.debug(f"Executing search: {query.query} ({query.angle})")

            response = await llm_service.generate_with_web_search(
                messages=[HumanMessage(content=query.query)],
                system_prompt=SEARCH_SYSTEM_PROMPT,
            )

            candidates = _extract_candidates_from_response(response.content)
            logger.info(f"Search '{query.angle}' found {len(candidates)} candidates")

            # Add category to each candidate
            for c in candidates:
                c["category"] = product_type

            return candidates

        except Exception as e:
            logger.warning(f"Search failed for '{query.query}': {e}")
            return []

    # Run all searches in parallel
    tasks = [single_search(q) for q in queries]
    results = await asyncio.gather(*tasks)

    # Flatten results
    all_candidates = []
    for result in results:
        all_candidates.extend(result)

    return all_candidates


def generate_field_definitions(product_type: str, requirements: dict) -> list[dict]:
    """
    Generate field definitions based on product category and user requirements.

    Args:
        product_type: Type of product (e.g., "electric kettle", "laptop")
        requirements: User requirements dict

    Returns:
        List of field definition dicts
    """
    logger.info(f"Generating field definitions for {product_type}")

    # Standard fields for all products
    fields = [
        {
            "category": "standard",
            "name": "name",
            "prompt": "Extract the product name",
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "price",
            "prompt": "Extract the product price",
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "rating",
            "prompt": "Extract the average customer rating",
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "official_url",
            "prompt": "Extract the official product URL",
            "data_type": "string",
        },
    ]

    # Category-specific fields
    if "kettle" in product_type.lower():
        fields.extend(
            [
                {
                    "category": "category",
                    "name": "capacity",
                    "prompt": "Extract capacity in liters",
                    "data_type": "number",
                },
                {
                    "category": "category",
                    "name": "wattage",
                    "prompt": "Extract power rating in watts",
                    "data_type": "number",
                },
                {
                    "category": "category",
                    "name": "material",
                    "prompt": "Extract primary material (plastic, stainless steel, glass)",
                    "data_type": "string",
                },
            ]
        )

        # User-driven fields based on priorities
        priorities = requirements.get("priorities", [])
        if (
            "temperature" in str(priorities).lower()
            or "temperature control" in str(requirements.get("must_haves", [])).lower()
        ):
            fields.append(
                {
                    "category": "user_driven",
                    "name": "temperature_control",
                    "prompt": "Does it have variable temperature control?",
                    "data_type": "boolean",
                }
            )

    elif "laptop" in product_type.lower():
        fields.extend(
            [
                {
                    "category": "category",
                    "name": "processor",
                    "prompt": "Extract CPU model",
                    "data_type": "string",
                },
                {
                    "category": "category",
                    "name": "ram",
                    "prompt": "Extract RAM capacity in GB",
                    "data_type": "number",
                },
                {
                    "category": "category",
                    "name": "storage",
                    "prompt": "Extract storage capacity and type",
                    "data_type": "string",
                },
                {
                    "category": "category",
                    "name": "screen_size",
                    "prompt": "Extract screen size in inches",
                    "data_type": "number",
                },
            ]
        )

    # Add qualification fields for requirement matching
    requirements_summary = _summarize_requirements(requirements)

    fields.append(
        {
            "category": "qualification",
            "name": "meets_requirements",
            "prompt": f"Does this product meet ALL these requirements: {requirements_summary}? Answer TRUE or FALSE only.",
            "data_type": "boolean",
        }
    )

    fields.append(
        {
            "category": "qualification",
            "name": "requirement_fit_notes",
            "prompt": f"Which of these requirements does this product meet or not meet: {requirements_summary}",
            "data_type": "string",
        }
    )

    logger.info(f"Generated {len(fields)} field definitions")
    return fields


async def explorer_step(state: AgentState) -> tuple[list[dict], list[dict]]:
    """
    Explorer sub-step - Find product candidates via web search.

    Args:
        state: Current workflow state

    Returns:
        Tuple of (candidates, field_definitions)
    """
    logger.info("Explorer: Starting candidate discovery")

    requirements = state.get("user_requirements", {})
    product_type = requirements.get("product_type", "product")

    settings = get_settings()
    llm_service = LLMService(settings)

    # Phase 1: Generate search queries (LLM decides)
    query_plan = await _generate_search_queries(llm_service, requirements)
    logger.info(f"Explorer: Generated {len(query_plan.queries)} search queries")

    # Phase 2: Execute parallel web searches
    raw_candidates = await _execute_parallel_searches(
        query_plan.queries,
        llm_service,
        product_type,
    )
    logger.info(f"Explorer: Found {len(raw_candidates)} raw candidates")

    # Phase 3: Deduplicate
    candidates = _deduplicate_candidates(raw_candidates)
    logger.info(f"Explorer: {len(candidates)} unique candidates after deduplication")

    # Warn if fewer than expected
    if len(candidates) < 10:
        logger.warning(f"Explorer: Only {len(candidates)} candidates found (expected 20+)")

    # Generate field definitions (including qualification fields)
    field_definitions = generate_field_definitions(product_type, requirements)

    return candidates, field_definitions


def _meets_requirements(candidate: dict) -> bool:
    """
    Check if a candidate meets requirements based on enriched data.

    Args:
        candidate: Enriched candidate dict

    Returns:
        True if meets requirements, False otherwise
    """
    meets_req = candidate.get("meets_requirements")
    # Handle various boolean representations
    if meets_req in [True, "TRUE", "True", "true", "Yes", "yes", "1"]:
        return True
    return False


async def enricher_step(
    candidates: list[dict],
    field_definitions: list[dict],
) -> dict:
    """
    Enricher sub-step - Build comparison table via Lattice enrichment with qualification filtering.

    Args:
        candidates: List of product candidates
        field_definitions: Field definitions for enrichment

    Returns:
        Comparison table dict with enriched data (only qualified candidates)
    """
    logger.info(f"Enricher: Starting enrichment for {len(candidates)} candidates")

    # Initialize Lattice service
    lattice_service = LatticeService()

    # Prepare field definitions for Lattice
    lattice_fields = lattice_service.prepare_field_definitions(field_definitions)

    # Enrich candidates
    results = await lattice_service.enrich_candidates(candidates, lattice_fields)

    # Process results and filter by qualification
    all_enriched = []
    qualified_candidates = []
    unqualified_count = 0
    failed_count = 0

    for result in results:
        if result.success:
            all_enriched.append(result.data)

            # Check if candidate meets requirements
            if _meets_requirements(result.data):
                qualified_candidates.append(result.data)
            else:
                unqualified_count += 1
                logger.debug(
                    f"Filtered out {result.candidate_id}: "
                    f"{result.data.get('requirement_fit_notes', 'N/A')}"
                )
        else:
            failed_count += 1
            logger.warning(f"Enrichment failed for {result.candidate_id}: {result.error}")

    logger.info(
        f"Enricher: {len(qualified_candidates)} qualified, "
        f"{unqualified_count} filtered out, {failed_count} failed"
    )

    # If no candidates qualified, return all with meets_requirements=FALSE for ADVISE to explain
    if not qualified_candidates and all_enriched:
        logger.warning("No candidates met requirements, returning all for ADVISE to explain")
        qualified_candidates = all_enriched

    # Build comparison table with qualified candidates
    comparison_table = {
        "fields": field_definitions,
        "candidates": qualified_candidates,
    }

    return comparison_table


def _format_fields_for_display(field_definitions: list[dict]) -> str:
    """
    Format field definitions for user display in HITL confirmation.

    Args:
        field_definitions: List of field definition dicts

    Returns:
        Formatted string for display
    """
    # Group by category
    standard = []
    category_specific = []
    user_driven = []

    for field in field_definitions:
        name = field.get("name", "unknown")
        cat = field.get("category", "standard")

        # Skip qualification fields (internal)
        if cat == "qualification":
            continue

        if cat == "standard":
            standard.append(name)
        elif cat == "category":
            category_specific.append(name)
        else:
            user_driven.append(name)

    parts = []
    if standard:
        parts.append(f"**Standard fields:** {', '.join(standard)}")
    if category_specific:
        parts.append(f"**Category-specific:** {', '.join(category_specific)}")
    if user_driven:
        parts.append(f"**Based on your priorities:** {', '.join(user_driven)}")

    return "\n".join(parts) if parts else "Standard comparison fields"


def _parse_hitl_choice(content: str) -> str | None:
    """
    Parse the choice from a HITL message.

    Args:
        content: Message content like "[HITL:fields:Enrich Now]"

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


async def research_node(state: AgentState) -> Command:
    """
    RESEARCH node - Find product candidates and build comparison table.

    This node has two sub-steps with HITL confirmation between them:
    1. Explorer (conditional) - Find candidates via web search
    2. [HITL checkpoint] - User confirms fields before enrichment
    3. Enricher - Build comparison table via Lattice

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

    # Check for HITL action at start
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content") and last_message.content.startswith("[HITL:fields:"):
            choice = _parse_hitl_choice(last_message.content)
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
                            "messages": [AIMessage(content="Something went wrong. Let me restart the search.")],
                            "current_node": "research",
                            "current_phase": "research",
                            **_clear_hitl_flags(),
                        },
                        goto="research",
                    )

                try:
                    # Run enricher with pending data
                    comparison_table = await enricher_step(existing_candidates, pending_fields)

                    num_candidates = len(comparison_table.get("candidates", []))
                    response_msg = f"Research complete! I found {num_candidates} products to compare."

                    logger.info("RESEARCH: Enrichment complete, transitioning to ADVISE")

                    return Command(
                        update={
                            "current_node": "research",
                            "current_phase": "advise",
                            "comparison_table": comparison_table,
                            "need_new_search": False,
                            "advise_has_presented": False,
                            "messages": [AIMessage(content=response_msg)],
                            **_clear_hitl_flags(),
                        },
                        goto="advise",
                    )
                except Exception:
                    logger.exception("RESEARCH enrichment error")
                    return Command(
                        update={
                            "messages": [AIMessage(content="I encountered an issue during enrichment.")],
                            "current_node": "research",
                            "current_phase": "error",
                            **_clear_hitl_flags(),
                        },
                        goto="advise",
                    )
            else:
                # User wants to modify fields
                logger.info("RESEARCH: User wants to modify fields")
                return Command(
                    update={
                        "messages": [AIMessage(content="What fields would you like me to add or change for the comparison? For example, you could ask for 'energy efficiency', 'warranty length', or 'weight'.")],
                        "current_node": "research",
                        "current_phase": "research",
                        **_clear_hitl_flags(),
                    },
                    goto="__end__",
                )

    # Check if we're awaiting confirmation (came back with non-HITL message)
    if awaiting_fields and messages:
        # User typed something instead of clicking button - treat as field modification request
        last_message = messages[-1]
        if hasattr(last_message, "content") and not last_message.content.startswith("[HITL:"):
            logger.info("RESEARCH: User provided text while awaiting fields confirmation")
            # TODO: In future, parse user's field requests and add to field definitions
            # For now, just proceed with enrichment
            pending_fields = state.get("pending_field_definitions", [])
            existing_candidates = state.get("candidates", [])

            if pending_fields and existing_candidates:
                try:
                    comparison_table = await enricher_step(existing_candidates, pending_fields)
                    num_candidates = len(comparison_table.get("candidates", []))
                    response_msg = f"Research complete! I found {num_candidates} products to compare."

                    return Command(
                        update={
                            "current_node": "research",
                            "current_phase": "advise",
                            "comparison_table": comparison_table,
                            "need_new_search": False,
                            "advise_has_presented": False,
                            "messages": [AIMessage(content=response_msg)],
                            **_clear_hitl_flags(),
                        },
                        goto="advise",
                    )
                except Exception:
                    logger.exception("RESEARCH enrichment error")

    try:
        # Step 1: Explorer (if needed)
        if need_new_search or not candidates:
            logger.info("Running Explorer sub-step")
            candidates, field_definitions = await explorer_step(state)

            # After Explorer completes, pause for HITL confirmation
            fields_summary = _format_fields_for_display(field_definitions)
            confirmation_message = (
                f"Found {len(candidates)} products!\n\n"
                f"I'll compare them on:\n{fields_summary}\n\n"
                f"Ready to analyze these products?"
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
        else:
            logger.info("Skipping Explorer (re-enrichment mode)")
            # Use existing candidates and field definitions
            comparison_table_data = state.get("comparison_table") or {}
            field_definitions = comparison_table_data.get("fields", [])

            # Defensive fallback if no field definitions exist
            if not field_definitions:
                logger.warning("No existing field definitions found, regenerating")
                requirements = state.get("user_requirements", {})
                product_type = requirements.get("product_type", "product")
                field_definitions = generate_field_definitions(product_type, requirements)

            # Step 2: Enricher (always when in re-enrichment mode)
            logger.info("Running Enricher sub-step")
            comparison_table = await enricher_step(candidates, field_definitions)

            # Build response message
            num_candidates = len(comparison_table.get("candidates", []))
            response_msg = f"Research complete! I found {num_candidates} products to compare."

            logger.info("RESEARCH complete, transitioning to ADVISE")

            return Command(
                update={
                    "current_node": "research",
                    "current_phase": "advise",
                    "candidates": candidates,
                    "comparison_table": comparison_table,
                    "need_new_search": False,
                    "advise_has_presented": False,
                    "messages": [AIMessage(content=response_msg)],
                    **_clear_hitl_flags(),
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
                **_clear_hitl_flags(),
            },
            goto="advise",  # Still proceed to ADVISE with error context
        )
