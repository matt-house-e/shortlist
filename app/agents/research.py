"""RESEARCH node - Find candidates and build comparison table."""

from pathlib import Path

import yaml
from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.models.state import AgentState
from app.services.lattice import MockLatticeService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"
EXPLORER_PROMPT_PATH = PROMPTS_DIR / "explorer.yaml"

with open(EXPLORER_PROMPT_PATH) as f:
    EXPLORER_PROMPTS = yaml.safe_load(f)


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
        if "temperature" in str(priorities).lower() or "temperature control" in str(
            requirements.get("must_haves", [])
        ).lower():
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

    # TODO: In production, this would:
    # 1. Formulate search queries based on requirements
    # 2. Use LLM service with web search (OpenAI Responses API)
    # 3. Parse results to extract official product URLs
    # 4. Deduplicate and filter
    # 5. Aim for 20-50 candidates

    # For now, generate mock candidates
    logger.info("Using mock candidate data (web search not yet integrated)")

    # Mock candidate data by product type
    mock_data = {
        "kettle": [
            {
                "name": "Fellow Stagg EKG Electric Pour-Over Kettle",
                "manufacturer": "Fellow",
                "official_url": "https://fellowproducts.com/products/stagg-ekg-electric-pour-over-kettle",
                "description": "Electric kettle with variable temperature control",
                "category": product_type,
            },
            {
                "name": "Bonavita 1.0L Variable Temperature Kettle",
                "manufacturer": "Bonavita",
                "official_url": "https://bonavitaworld.com/products/10l-variable-temperature-kettle",
                "description": "Compact kettle with precise temperature control",
                "category": product_type,
            },
            {
                "name": "Cuisinart CPK-17 PerfecTemp Kettle",
                "manufacturer": "Cuisinart",
                "official_url": "https://www.cuisinart.com/shopping/appliances/kettles/cpk-17",
                "description": "1.7-liter cordless electric kettle",
                "category": product_type,
            },
            {
                "name": "Breville BKE820XL Variable-Temperature Kettle",
                "manufacturer": "Breville",
                "official_url": "https://www.breville.com/us/en/products/kettles/bke820.html",
                "description": "Premium kettle with 5 temperature presets",
                "category": product_type,
            },
            {
                "name": "OXO Brew Adjustable Temperature Kettle",
                "manufacturer": "OXO",
                "official_url": "https://www.oxo.com/brew-adjustable-temperature-kettle.html",
                "description": "Precision pour kettle for coffee and tea",
                "category": product_type,
            },
        ],
        "laptop": [
            {
                "name": "Dell XPS 13",
                "manufacturer": "Dell",
                "official_url": "https://www.dell.com/en-us/shop/dell-laptops/xps-13-laptop/spd/xps-13-9340-laptop",
                "description": "Compact 13-inch ultrabook with Intel processors",
                "category": product_type,
            },
            {
                "name": "MacBook Air M3",
                "manufacturer": "Apple",
                "official_url": "https://www.apple.com/macbook-air/",
                "description": "Lightweight laptop with Apple Silicon",
                "category": product_type,
            },
            {
                "name": "Lenovo ThinkPad X1 Carbon",
                "manufacturer": "Lenovo",
                "official_url": "https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpadx1/thinkpad-x1-carbon-gen-11",
                "description": "Business laptop with robust build quality",
                "category": product_type,
            },
            {
                "name": "HP Spectre x360",
                "manufacturer": "HP",
                "official_url": "https://www.hp.com/us-en/shop/pdp/hp-spectre-x360-2-in-1-laptop-14",
                "description": "2-in-1 convertible laptop with touchscreen",
                "category": product_type,
            },
            {
                "name": "ASUS ZenBook 14",
                "manufacturer": "ASUS",
                "official_url": "https://www.asus.com/laptops/for-home/zenbook/zenbook-14-oled-ux3405",
                "description": "Premium ultrabook with OLED display",
                "category": product_type,
            },
        ],
    }

    # Select mock data based on product type or use generic fallback
    candidates = None
    for key in mock_data:
        if key in product_type.lower():
            candidates = mock_data[key]
            break

    # Fallback to generic product if no match
    if candidates is None:
        logger.warning(f"No mock data for product type '{product_type}', using generic fallback")
        candidates = [
            {
                "name": f"Generic {product_type.title()} Option 1",
                "manufacturer": "Unknown",
                "official_url": f"https://example.com/product-1",
                "description": f"A {product_type} product",
                "category": product_type,
            },
            {
                "name": f"Generic {product_type.title()} Option 2",
                "manufacturer": "Unknown",
                "official_url": f"https://example.com/product-2",
                "description": f"Another {product_type} product",
                "category": product_type,
            },
            {
                "name": f"Generic {product_type.title()} Option 3",
                "manufacturer": "Unknown",
                "official_url": f"https://example.com/product-3",
                "description": f"Yet another {product_type} product",
                "category": product_type,
            },
        ]

    # Generate field definitions
    field_definitions = generate_field_definitions(product_type, requirements)

    logger.info(f"Explorer: Found {len(candidates)} candidates")
    return candidates, field_definitions


async def enricher_step(
    candidates: list[dict],
    field_definitions: list[dict],
) -> dict:
    """
    Enricher sub-step - Build comparison table via Lattice enrichment.

    Args:
        candidates: List of product candidates
        field_definitions: Field definitions for enrichment

    Returns:
        Comparison table dict with enriched data
    """
    logger.info(f"Enricher: Starting enrichment for {len(candidates)} candidates")

    # Initialize Lattice service (using mock for now)
    lattice_service = MockLatticeService()

    # Prepare field definitions for Lattice
    lattice_fields = lattice_service.prepare_field_definitions(field_definitions)

    # Enrich candidates
    results = await lattice_service.enrich_candidates(candidates, lattice_fields)

    # Build comparison table
    comparison_table = {
        "fields": field_definitions,
        "candidates": [],
    }

    for result in results:
        if result.success:
            comparison_table["candidates"].append(result.data)
        else:
            logger.warning(f"Enrichment failed for {result.candidate_id}: {result.error}")
            # Include incomplete candidate with available data
            comparison_table["candidates"].append(
                {
                    "name": result.candidate_id,
                    "error": result.error,
                }
            )

    successful = sum(1 for r in results if r.success)
    logger.info(f"Enricher: Completed with {successful}/{len(results)} successful")

    return comparison_table


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
    field_definitions = []

    try:
        # Step 1: Explorer (if needed)
        if need_new_search or not candidates:
            logger.info("Running Explorer sub-step")
            candidates, field_definitions = await explorer_step(state)
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

        # Step 2: Enricher (always)
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
                "messages": [AIMessage(content=response_msg)],
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
            },
            goto="advise",  # Still proceed to ADVISE with error context
        )
