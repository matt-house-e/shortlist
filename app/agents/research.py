"""RESEARCH node - Find candidates and build comparison table."""

import asyncio
import json
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config.settings import get_settings
from app.models.schemas.shortlist import (
    Candidate,
    CellStatus,
    ComparisonTable,
    FieldDefinition,
    SearchQuery,
    SearchQueryPlan,
)
from app.models.state import AgentState
from app.services.field_generation import get_field_generation_service
from app.services.lattice import LatticeService
from app.services.llm import LLMService
from app.services.search_strategy import get_search_strategy_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"
EXPLORER_PROMPT_PATH = PROMPTS_DIR / "explorer.yaml"

with open(EXPLORER_PROMPT_PATH) as f:
    EXPLORER_PROMPTS = yaml.safe_load(f)


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


async def _generate_search_queries(
    llm_service: LLMService,
    requirements: dict,
) -> SearchQueryPlan:
    """
    Generate diverse search queries using the SearchStrategyService.

    Uses a category-aware knowledge base to generate queries across:
    - Review sites (Wirecutter, TechRadar, Which?, etc.)
    - Reddit communities (r/BuyItForLife, category-specific subreddits)
    - Top brand catalogs
    - Comparison articles
    - Budget and premium options
    - Feature-focused searches
    - Use case searches
    - Alternative/underrated product searches

    Args:
        llm_service: LLM service instance
        requirements: User requirements dict

    Returns:
        SearchQueryPlan with 10-15 diverse queries
    """
    try:
        # Use the search strategy service with category knowledge base
        search_service = get_search_strategy_service()
        result = await search_service.generate_queries(requirements, llm_service)

        # Convert to SearchQueryPlan from shortlist schema
        queries = [
            SearchQuery(
                query=q.query,
                angle=q.angle,
                expected_results=q.expected_results,
            )
            for q in result.queries
        ]

        plan = SearchQueryPlan(
            queries=queries,
            strategy_notes=result.strategy_notes,
            brands_covered=result.brands_covered,
            sources_covered=result.sources_covered,
        )

        # Log detailed breakdown
        angles = [q.angle for q in queries]
        angle_counts = {a: angles.count(a) for a in set(angles)}
        logger.info(f"Generated {len(queries)} diverse queries")
        logger.info(f"Query angles: {angle_counts}")
        logger.info(f"Brands covered: {result.brands_covered}")

        return plan

    except Exception as e:
        logger.warning(f"Search strategy generation failed, using fallback: {e}")
        product_type = requirements.get("product_type", "product")
        budget_max = requirements.get("budget_max")
        budget_str = f" under £{budget_max}" if budget_max else ""

        fallback_queries = [
            SearchQuery(query=f"best {product_type}{budget_str} 2025 reviews", angle="REVIEW_SITE"),
            SearchQuery(query=f"{product_type} recommendations reddit", angle="REDDIT"),
            SearchQuery(query=f"top rated {product_type} comparison 2025", angle="COMPARISON"),
            SearchQuery(query=f"{product_type} alternatives underrated 2025", angle="ALTERNATIVES"),
        ]

        return SearchQueryPlan(
            queries=fallback_queries,
            strategy_notes="Fallback queries due to generation error",
            brands_covered=[],
            sources_covered=["review sites", "reddit"],
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


# System prompt for web search to extract product candidates
SEARCH_SYSTEM_PROMPT = """You are a product researcher. Search for products matching the query.
For each product found, extract:
- Full product name (be specific, include model numbers)
- Manufacturer/brand
- Official product URL (manufacturer site preferred, not retailer)
- Brief description

Return results as a JSON array:
[
    {"name": "Product Name Model X123", "manufacturer": "Brand", "official_url": "https://...", "description": "Brief description"},
    ...
]

IMPORTANT:
- Find 8-15 DISTINCT products per search
- Include model numbers/variants when available
- Prioritize manufacturer URLs over retailer URLs
- Include a mix of popular and lesser-known options
- Don't repeat the same product with different names"""


async def _execute_parallel_searches(
    queries: list[SearchQuery],
    llm_service: LLMService,
    product_type: str,
) -> list[dict]:
    """
    Execute multiple web searches in parallel.

    Args:
        queries: List of search queries (10-15 diverse queries)
        llm_service: LLM service instance
        product_type: Type of product for context

    Returns:
        List of all candidates from all searches (not yet deduplicated)
    """
    # Log all queries being executed
    logger.info(f"Executing {len(queries)} parallel searches:")
    for i, q in enumerate(queries, 1):
        logger.info(f"  [{i}] ({q.angle}) {q.query[:60]}...")

    async def single_search(query: SearchQuery, index: int) -> list[dict]:
        """Execute a single web search and extract candidates."""
        try:
            logger.debug(f"[{index}] Starting search: {query.query}")

            response = await llm_service.generate_with_web_search(
                messages=[HumanMessage(content=query.query)],
                system_prompt=SEARCH_SYSTEM_PROMPT,
            )

            candidates = _extract_candidates_from_response(response.content)

            # Log with angle and count
            logger.info(
                f"[{index}] {query.angle}: {len(candidates)} candidates "
                f"(query: {query.query[:40]}...)"
            )

            # Add metadata to each candidate
            for c in candidates:
                c["category"] = product_type
                c["source_angle"] = query.angle
                c["source_query"] = query.query

            return candidates

        except Exception as e:
            logger.warning(f"[{index}] Search failed for '{query.query[:40]}...': {e}")
            return []

    # Run all searches in parallel
    tasks = [single_search(q, i) for i, q in enumerate(queries, 1)]
    results = await asyncio.gather(*tasks)

    # Flatten results and log summary
    all_candidates = []
    angle_counts: dict[str, int] = {}

    for i, result in enumerate(results):
        all_candidates.extend(result)
        if queries[i].angle not in angle_counts:
            angle_counts[queries[i].angle] = 0
        angle_counts[queries[i].angle] += len(result)

    logger.info(f"Total raw candidates: {len(all_candidates)}")
    logger.info(f"Candidates by angle: {angle_counts}")

    return all_candidates


async def generate_field_definitions(
    product_type: str,
    requirements: dict,
    llm_service: LLMService,
) -> list[dict]:
    """
    Generate field definitions based on product category and user requirements.

    Uses LLM to determine appropriate category-specific fields based on its knowledge
    of the product type. Standard fields and qualification fields are always included.

    Args:
        product_type: Type of product (e.g., "electric kettle", "laptop")
        requirements: User requirements dict
        llm_service: LLM service for generating category-specific fields

    Returns:
        List of field definition dicts (11-16 total: 4 standard + 5-10 category + 2 qualification)
    """
    logger.info(f"Generating field definitions for {product_type}")

    # Standard fields for all products - with improved extraction prompts
    fields = [
        {
            "category": "standard",
            "name": "name",
            "prompt": (
                "Extract the full product name including brand and model number. "
                "Look for the official product title. Format: 'Brand Model Name'."
            ),
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "price",
            "prompt": (
                "Extract the current retail price with currency symbol. "
                "Use the main price, not sale/discount price. "
                "If a range is given, use the starting price. Format: '$XX.XX' or '£XX.XX'."
            ),
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "rating",
            "prompt": (
                "Extract the average customer rating. "
                "Look for star ratings, scores, or review averages. "
                "Format as 'X.X/5' or 'X/10'. If percentage, convert to /5 scale."
            ),
            "data_type": "string",
        },
        {
            "category": "standard",
            "name": "official_url",
            "prompt": (
                "Extract the official product page URL from the manufacturer's website. "
                "Prefer manufacturer URLs over retailer URLs (Amazon, Best Buy, etc.). "
                "If no official URL found, use the most authoritative product page."
            ),
            "data_type": "string",
        },
    ]

    # Generate category-specific fields using LLM
    logger.info("Generating category-specific fields via LLM...")
    field_service = get_field_generation_service()
    category_fields = await field_service.generate_fields(requirements, llm_service)

    # Add category-specific fields
    fields.extend(category_fields)
    logger.info(f"Added {len(category_fields)} category-specific fields")

    # Add qualification fields for requirement matching
    requirements_summary = _summarize_requirements(requirements)

    fields.append(
        {
            "category": "qualification",
            "name": "meets_requirements",
            "prompt": (
                f"Does this product meet ALL these requirements: {requirements_summary}? "
                "Carefully check each requirement against the product specs. "
                "Answer TRUE only if ALL requirements are met. Answer FALSE if any requirement is not met or unclear."
            ),
            "data_type": "boolean",
        }
    )

    fields.append(
        {
            "category": "qualification",
            "name": "requirement_fit_notes",
            "prompt": (
                f"For each of these requirements: {requirements_summary} - "
                "indicate which are MET, NOT MET, or UNCLEAR. "
                "Be specific about why each requirement is or isn't satisfied."
            ),
            "data_type": "string",
        }
    )

    logger.info(f"Generated {len(fields)} total field definitions")
    return fields


def _get_or_create_living_table(state: AgentState) -> ComparisonTable:
    """
    Get existing living table from state or create a new one.

    Args:
        state: Current workflow state

    Returns:
        ComparisonTable instance
    """
    living_table_data = state.get("living_table")
    if living_table_data:
        return ComparisonTable.model_validate(living_table_data)
    return ComparisonTable()


def _add_candidates_to_table(
    table: ComparisonTable,
    candidates: list[dict],
) -> tuple[int, int]:
    """
    Add candidates to the living table with deduplication.

    Args:
        table: ComparisonTable instance
        candidates: List of candidate dicts from explorer

    Returns:
        Tuple of (added_count, duplicate_count)
    """
    added = 0
    duplicates = 0

    for candidate_dict in candidates:
        # Convert dict to Candidate model
        candidate = Candidate(
            name=candidate_dict.get("name", "Unknown"),
            manufacturer=candidate_dict.get("manufacturer", "Unknown"),
            official_url=candidate_dict.get("official_url"),
            description=candidate_dict.get("description"),
            category=candidate_dict.get("category"),
        )

        # Try to add (returns None if duplicate)
        row_id = table.add_row(
            candidate=candidate,
            source_query=candidate_dict.get("source_query"),
        )

        if row_id:
            added += 1
        else:
            duplicates += 1

    logger.info(f"Added {added} candidates to table, {duplicates} duplicates skipped")
    return added, duplicates


def _add_requested_fields_to_table(
    table: ComparisonTable,
    requested_fields: list[str],
) -> list[str]:
    """
    Add user-requested fields to the table.

    Creates FieldDefinition for each requested field name and adds it to the table.
    This marks all existing rows as PENDING for the new fields.

    Args:
        table: ComparisonTable instance
        requested_fields: List of field names requested by user

    Returns:
        List of field names that were actually added (not already present)
    """
    added_fields = []

    for field_name in requested_fields:
        # Check if field already exists
        existing_names = {f.name for f in table.fields}
        if field_name in existing_names:
            logger.debug(f"Field '{field_name}' already exists, skipping")
            continue

        # Create field definition for user-requested field
        field_def = FieldDefinition(
            name=field_name,
            prompt=f"Extract or determine the {field_name} for this product",
            data_type="string",
            category="user_driven",
        )

        table.add_field(field_def)
        added_fields.append(field_name)
        logger.info(f"Added user-requested field: {field_name}")

    return added_fields


def _build_field_definitions_list(table: ComparisonTable) -> list[dict]:
    """
    Convert table's FieldDefinition objects to dict list for Lattice.

    Args:
        table: ComparisonTable instance

    Returns:
        List of field definition dicts
    """
    return [
        {
            "category": str(f.category.value) if hasattr(f.category, "value") else str(f.category),
            "name": f.name,
            "prompt": f.prompt,
            "data_type": str(f.data_type.value)
            if hasattr(f.data_type, "value")
            else str(f.data_type),
        }
        for f in table.fields
    ]


async def explorer_step(state: AgentState) -> tuple[list[dict], list[dict]]:
    """
    Explorer sub-step - Find product candidates via web search.

    Uses the SearchStrategyService to generate diverse queries across:
    - Review sites (Wirecutter, TechRadar, Which?, etc.)
    - Reddit communities (category-specific subreddits)
    - Top brand catalogs
    - Comparison articles
    - Budget/premium options
    - Feature-focused and use-case searches

    Args:
        state: Current workflow state

    Returns:
        Tuple of (candidates, field_definitions)
    """
    logger.info("=" * 60)
    logger.info("Explorer: Starting candidate discovery")
    logger.info("=" * 60)

    requirements = state.get("user_requirements", {})
    product_type = requirements.get("product_type", "product")

    logger.info(f"Product type: {product_type}")
    logger.info(f"Budget: {requirements.get('budget_max', 'No limit')}")
    logger.info(f"Must-haves: {requirements.get('must_haves', [])}")

    settings = get_settings()
    llm_service = LLMService(settings)

    # Phase 1: Generate diverse search queries using SearchStrategyService
    logger.info("-" * 40)
    logger.info("Phase 1: Generating diverse search queries")
    logger.info("-" * 40)

    query_plan = await _generate_search_queries(llm_service, requirements)

    logger.info(f"Generated {len(query_plan.queries)} queries")
    if query_plan.brands_covered:
        logger.info(f"Brands covered: {', '.join(query_plan.brands_covered)}")
    if query_plan.sources_covered:
        logger.info(f"Sources covered: {', '.join(query_plan.sources_covered)}")

    # Phase 2: Execute parallel web searches
    logger.info("-" * 40)
    logger.info("Phase 2: Executing parallel web searches")
    logger.info("-" * 40)

    raw_candidates = await _execute_parallel_searches(
        query_plan.queries,
        llm_service,
        product_type,
    )
    logger.info(f"Raw candidates found: {len(raw_candidates)}")

    # Phase 3: Deduplicate
    logger.info("-" * 40)
    logger.info("Phase 3: Deduplicating candidates")
    logger.info("-" * 40)

    candidates = _deduplicate_candidates(raw_candidates)
    dedup_rate = (1 - len(candidates) / max(len(raw_candidates), 1)) * 100
    logger.info(f"Unique candidates: {len(candidates)} (removed {dedup_rate:.1f}% duplicates)")

    # Log brand diversity
    brands = {c.get("manufacturer", "Unknown") for c in candidates}
    logger.info(f"Brand diversity: {len(brands)} unique brands")

    # Warn if fewer than expected
    if len(candidates) < 20:
        logger.warning(f"Only {len(candidates)} candidates found (target: 40+)")

    # Generate field definitions (including category-specific and qualification fields)
    logger.info("-" * 40)
    logger.info("Phase 4: Generating category-specific field definitions")
    logger.info("-" * 40)

    field_definitions = await generate_field_definitions(product_type, requirements, llm_service)

    logger.info("=" * 60)
    logger.info(f"Explorer complete: {len(candidates)} candidates, {len(field_definitions)} fields")
    logger.info("=" * 60)

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

    DEPRECATED: Use enrich_living_table() for incremental enrichment.

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


async def enrich_living_table(table: ComparisonTable) -> ComparisonTable:
    """
    Enrich PENDING cells in the living table via Lattice.

    Only enriches cells with PENDING or FLAGGED status, making this efficient
    for incremental updates (adding new fields or new rows).

    Args:
        table: ComparisonTable with cells to enrich

    Returns:
        Updated ComparisonTable with enriched cells
    """
    pending_cells = table.get_pending_cells()

    if not pending_cells:
        logger.info("No pending cells to enrich")
        return table

    logger.info(f"Enriching {len(pending_cells)} pending cells")

    # Group pending cells by row for batch processing
    rows_to_enrich: dict[str, list[str]] = {}
    for row_id, field_name in pending_cells:
        if row_id not in rows_to_enrich:
            rows_to_enrich[row_id] = []
        rows_to_enrich[row_id].append(field_name)

    # Prepare candidates for Lattice (need full candidate data)
    candidates_for_lattice = []
    row_id_to_index: dict[str, int] = {}

    for idx, row_id in enumerate(rows_to_enrich.keys()):
        row = table.rows[row_id]
        candidates_for_lattice.append(
            {
                "name": row.candidate.name,
                "manufacturer": row.candidate.manufacturer,
                "official_url": row.candidate.official_url,
                "description": row.candidate.description,
                "category": row.candidate.category,
            }
        )
        row_id_to_index[row_id] = idx

    # Get field definitions for fields that need enrichment
    fields_to_enrich = set()
    for field_names in rows_to_enrich.values():
        fields_to_enrich.update(field_names)

    field_definitions = [
        {
            "category": str(f.category.value) if hasattr(f.category, "value") else str(f.category),
            "name": f.name,
            "prompt": f.prompt,
            "data_type": str(f.data_type.value)
            if hasattr(f.data_type, "value")
            else str(f.data_type),
        }
        for f in table.fields
        if f.name in fields_to_enrich
    ]

    if not field_definitions:
        logger.warning("No field definitions for pending fields")
        return table

    # Initialize Lattice service and enrich
    lattice_service = LatticeService()
    lattice_fields = lattice_service.prepare_field_definitions(field_definitions)

    results = await lattice_service.enrich_candidates(candidates_for_lattice, lattice_fields)

    # Update table cells with results
    enriched_count = 0
    failed_count = 0

    for row_id, fields_for_row in rows_to_enrich.items():
        idx = row_id_to_index[row_id]
        result = results[idx] if idx < len(results) else None

        if result and result.success:
            for field_name in fields_for_row:
                value = result.data.get(field_name)
                table.update_cell(
                    row_id=row_id,
                    field_name=field_name,
                    value=value,
                    status=CellStatus.ENRICHED,
                    source="lattice",
                )
                enriched_count += 1
        else:
            error_msg = result.error if result else "No result"
            for field_name in fields_for_row:
                table.update_cell(
                    row_id=row_id,
                    field_name=field_name,
                    value=None,
                    status=CellStatus.FAILED,
                    source="lattice",
                    error=error_msg,
                )
                failed_count += 1

    logger.info(f"Enrichment complete: {enriched_count} cells enriched, {failed_count} failed")

    return table


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
                            "messages": [
                                AIMessage(
                                    content="Something went wrong. Let me restart the search."
                                )
                            ],
                            "current_node": "research",
                            "current_phase": "research",
                            **_clear_hitl_flags(),
                        },
                        goto="research",
                    )

                try:
                    # Build living table and enrich
                    living_table = _get_or_create_living_table(state)

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
                    _add_candidates_to_table(living_table, existing_candidates)

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
                            **_clear_hitl_flags(),
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
                            **_clear_hitl_flags(),
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
            pending_fields = state.get("pending_field_definitions", [])
            existing_candidates = state.get("candidates", [])

            if pending_fields and existing_candidates:
                try:
                    # Build living table and enrich
                    living_table = _get_or_create_living_table(state)

                    if not living_table.fields:
                        for field_dict in pending_fields:
                            field_def = FieldDefinition(
                                name=field_dict["name"],
                                prompt=field_dict["prompt"],
                                data_type=field_dict["data_type"],
                                category=field_dict["category"],
                            )
                            living_table.add_field(field_def)

                    _add_candidates_to_table(living_table, existing_candidates)
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
                            **_clear_hitl_flags(),
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
            living_table = _get_or_create_living_table(state)

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
                        **_clear_hitl_flags(),
                    },
                    goto="research",
                )

            # Add the requested fields to the table (marks all rows PENDING for these fields)
            added_fields = _add_requested_fields_to_table(living_table, requested_fields)

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
                        **_clear_hitl_flags(),
                    },
                    goto="advise",
                )

            # Enrich only the new fields (cells are PENDING only for new fields)
            logger.info(
                f"Enriching {len(added_fields)} new fields for {living_table.get_row_count()} products"
            )
            living_table = await enrich_living_table(living_table)

            # Build legacy comparison table for backward compatibility
            field_defs_list = _build_field_definitions_list(living_table)
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
                    **_clear_hitl_flags(),
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

        # =====================================================================
        # PATH 3: Re-enrich (need_new_search=False, no requested_fields)
        # =====================================================================
        logger.info("Skipping Explorer (re-enrichment mode)")

        # Get existing living table or build from legacy data
        living_table = _get_or_create_living_table(state)

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
            _add_candidates_to_table(living_table, candidates)

        # Enrich pending cells
        living_table = await enrich_living_table(living_table)

        # Also run legacy enricher for backward compatibility
        field_defs_list = _build_field_definitions_list(living_table)
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
