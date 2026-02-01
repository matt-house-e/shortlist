"""Explorer sub-step - Find product candidates via web search."""

import asyncio
import json
from pathlib import Path

import yaml

from app.config.settings import get_settings
from app.models.schemas.shortlist import SearchQuery, SearchQueryPlan
from app.models.state import AgentState
from app.services.field_generation import get_field_generation_service
from app.services.llm import LLMService, get_llm_service
from app.services.search_strategy import get_search_strategy_service
from app.utils.logger import get_logger
from app.utils.retry import web_search_retry

logger = get_logger(__name__)

# Load prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"
EXPLORER_PROMPT_PATH = PROMPTS_DIR / "explorer.yaml"

with open(EXPLORER_PROMPT_PATH) as f:
    EXPLORER_PROMPTS = yaml.safe_load(f)

# System prompt for web search to extract product candidates
SEARCH_SYSTEM_PROMPT = """You are a product researcher. Search for products matching the query.
For each product found, extract:
- Full product name (be specific, include model numbers)
- Manufacturer/brand
- Brief description

Return results as a JSON array:
[
    {"name": "Product Name Model X123", "manufacturer": "Brand", "description": "Brief description"},
    ...
]

IMPORTANT:
- Find 8-15 DISTINCT products per search
- Include model numbers/variants when available
- Include a mix of popular and lesser-known options
- Don't repeat the same product with different names
- Do NOT include URLs - they will be extracted from citations automatically"""


def summarize_requirements(requirements: dict) -> str:
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

    specifications = requirements.get("specifications", [])
    if specifications:
        parts.append(f"Specifications: {', '.join(specifications)}")

    constraints = requirements.get("constraints", [])
    if constraints:
        parts.append(f"Avoid: {', '.join(constraints)}")

    return "; ".join(parts)


async def generate_search_queries(
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


def match_citation_to_product(
    product_name: str,
    manufacturer: str,
    citations: list,
) -> str | None:
    """
    Find the best matching citation URL for a product.

    Args:
        product_name: Full product name
        manufacturer: Brand/manufacturer name
        citations: List of Citation objects with url and title

    Returns:
        Best matching URL or None
    """
    if not citations:
        return None

    # Normalize for matching
    name_lower = product_name.lower()
    mfr_lower = manufacturer.lower() if manufacturer else ""

    # Extract key terms from product name (first few words, model numbers)
    name_terms = [t for t in name_lower.split()[:4] if len(t) > 2]

    best_match = None
    best_score = 0

    for citation in citations:
        url_lower = citation.url.lower()
        title_lower = (citation.title or "").lower()

        score = 0

        # Check manufacturer in URL or title (strong signal)
        if mfr_lower and len(mfr_lower) > 2:
            if mfr_lower in url_lower:
                score += 3
            if mfr_lower in title_lower:
                score += 2

        # Check product name terms
        for term in name_terms:
            if term in url_lower:
                score += 1
            if term in title_lower:
                score += 1

        # Prefer manufacturer domains over retailers
        retailer_domains = ["amazon", "bestbuy", "walmart", "target", "ebay", "newegg"]
        is_retailer = any(r in url_lower for r in retailer_domains)
        if is_retailer:
            score -= 1  # Slight penalty for retailers

        if score > best_score:
            best_score = score
            best_match = citation.url

    # Only return if we have a reasonable match (at least manufacturer matched)
    return best_match if best_score >= 2 else None


def extract_candidates_from_response(
    response_content: str,
    citations: list | None = None,
) -> list[dict]:
    """
    Extract product candidates from web search response.

    Uses real URLs from citations instead of LLM-hallucinated URLs.

    Args:
        response_content: Raw response content from web search
        citations: List of Citation objects from web search (with real URLs)

    Returns:
        List of candidate dicts
    """
    candidates = []
    citations = citations or []

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
                        name = item.get("name", "")
                        manufacturer = item.get("manufacturer", "Unknown")

                        # Match citation URL instead of using hallucinated URL
                        matched_url = match_citation_to_product(name, manufacturer, citations)

                        # Log when we replace a hallucinated URL
                        hallucinated_url = item.get("official_url")
                        if hallucinated_url and matched_url:
                            logger.debug(
                                f"Replaced hallucinated URL for {name}: "
                                f"{hallucinated_url} -> {matched_url}"
                            )
                        elif hallucinated_url and not matched_url:
                            logger.debug(
                                f"No citation match for {name}, discarding hallucinated URL"
                            )

                        candidates.append(
                            {
                                "name": name,
                                "manufacturer": manufacturer,
                                "official_url": matched_url,  # Use real URL from citations
                                "description": item.get("description", ""),
                            }
                        )
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from response: {e}")

    return candidates


def normalize_name(name: str) -> str:
    """Normalize product name for deduplication comparison."""
    return name.lower().strip().replace("-", " ").replace("_", " ")


def deduplicate_candidates(candidates: list[dict]) -> list[dict]:
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

        normalized = normalize_name(name)

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


@web_search_retry
async def _execute_web_search(llm_service: LLMService, query: str) -> tuple:
    """Execute a single web search with retry logic for transient failures."""
    from langchain_core.messages import HumanMessage

    response = await llm_service.generate_with_web_search(
        messages=[HumanMessage(content=query)],
        system_prompt=SEARCH_SYSTEM_PROMPT,
    )
    return response.content, response.citations


async def execute_parallel_searches(
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

            # Use retryable helper for web search
            content, citations = await _execute_web_search(llm_service, query.query)

            # Pass citations to extract real URLs instead of hallucinated ones
            candidates = extract_candidates_from_response(content, citations)

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
            "name": "official_url",
            "prompt": (
                "Select the official product page URL from the 'Source:' URLs provided in the search results. "
                "ONLY use URLs that appear in the source context - NEVER generate or guess URLs. "
                "Prefer manufacturer URLs over retailer URLs (Amazon, Best Buy, etc.). "
                "If no suitable URL is found in the sources, return null."
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
    requirements_summary = summarize_requirements(requirements)

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

    llm_service = get_llm_service()

    # Phase 1: Generate diverse search queries using SearchStrategyService
    logger.info("-" * 40)
    logger.info("Phase 1: Generating diverse search queries")
    logger.info("-" * 40)

    query_plan = await generate_search_queries(llm_service, requirements)

    logger.info(f"Generated {len(query_plan.queries)} queries")
    if query_plan.brands_covered:
        logger.info(f"Brands covered: {', '.join(query_plan.brands_covered)}")
    if query_plan.sources_covered:
        logger.info(f"Sources covered: {', '.join(query_plan.sources_covered)}")

    # Phase 2: Execute parallel web searches
    logger.info("-" * 40)
    logger.info("Phase 2: Executing parallel web searches")
    logger.info("-" * 40)

    raw_candidates = await execute_parallel_searches(
        query_plan.queries,
        llm_service,
        product_type,
    )
    logger.info(f"Raw candidates found: {len(raw_candidates)}")

    # Phase 3: Deduplicate
    logger.info("-" * 40)
    logger.info("Phase 3: Deduplicating candidates")
    logger.info("-" * 40)

    candidates = deduplicate_candidates(raw_candidates)
    dedup_rate = (1 - len(candidates) / max(len(raw_candidates), 1)) * 100
    logger.info(f"Unique candidates: {len(candidates)} (removed {dedup_rate:.1f}% duplicates)")

    # Apply max_products limit from settings
    settings = get_settings()
    max_products = settings.max_products
    if len(candidates) > max_products:
        logger.info(
            f"Limiting candidates from {len(candidates)} to {max_products} (max_products setting)"
        )
        candidates = candidates[:max_products]

    # Log brand diversity
    brands = {c.get("manufacturer", "Unknown") for c in candidates}
    logger.info(f"Brand diversity: {len(brands)} unique brands")

    # Warn if fewer than expected minimum
    if len(candidates) < 10:
        logger.warning(f"Only {len(candidates)} candidates found (expected at least 10)")

    # Generate field definitions (including category-specific and qualification fields)
    logger.info("-" * 40)
    logger.info("Phase 4: Generating category-specific field definitions")
    logger.info("-" * 40)

    field_definitions = await generate_field_definitions(product_type, requirements, llm_service)

    logger.info("=" * 60)
    logger.info(f"Explorer complete: {len(candidates)} candidates, {len(field_definitions)} fields")
    logger.info("=" * 60)

    return candidates, field_definitions
