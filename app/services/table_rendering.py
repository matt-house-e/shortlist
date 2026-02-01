"""Table rendering service for preparing ProductTable React component props."""

from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.models.schemas.shortlist import CellStatus, ComparisonTable, FieldCategory
from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Maximum products to show in the table
MAX_DISPLAY_PRODUCTS = 10

# Target number of fields to display
MIN_DISPLAY_FIELDS = 4
MAX_DISPLAY_FIELDS = 5


class SelectedFields(BaseModel):
    """LLM output schema for field selection."""

    fields: list[str] = Field(
        ...,
        description="List of 4-5 field names most relevant for comparison",
        min_length=MIN_DISPLAY_FIELDS,
        max_length=MAX_DISPLAY_FIELDS,
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why these fields were selected",
    )


def select_top_products(
    table: ComparisonTable,
    max_count: int = MAX_DISPLAY_PRODUCTS,
) -> list[str]:
    """
    Select top products for display based on qualification and enrichment completeness.

    Selection criteria (in order):
    1. Products that meet_requirements = True first
    2. Within each group, sort by enrichment completeness (fewer pending cells = higher rank)

    Args:
        table: The comparison table with product rows
        max_count: Maximum number of products to select

    Returns:
        List of row_ids for the top products
    """
    if not table.rows:
        return []

    def enrichment_score(row_id: str) -> tuple[int, int]:
        """
        Calculate sorting key for a row.

        Returns tuple of (qualification_score, enriched_count) for sorting.
        - qualification_score: 0 if meets requirements (sort first), 1 otherwise
        - enriched_count: number of enriched cells (higher = better, so negate)
        """
        row = table.rows[row_id]

        # Qualification: True sorts first (0 < 1)
        qual_score = 0 if row.meets_requirements is True else 1

        # Count enriched cells (more is better)
        enriched_count = sum(1 for cell in row.cells.values() if cell.status == CellStatus.ENRICHED)

        # Negate enriched count so higher counts sort first
        return (qual_score, -enriched_count)

    # Sort row_ids by enrichment score
    sorted_row_ids = sorted(table.rows.keys(), key=enrichment_score)

    return sorted_row_ids[:max_count]


async def select_key_fields(
    table: ComparisonTable,
    user_requirements: dict[str, Any] | None,
    llm_service: LLMService,
) -> list[str]:
    """
    Use LLM to select 5-7 most relevant fields for comparison display.

    The LLM considers:
    - User's must-haves and priorities
    - Available fields in the table
    - Which fields are most useful for product comparison

    Args:
        table: The comparison table with field definitions
        user_requirements: User requirements dict (product_type, must_haves, priorities, etc.)
        llm_service: LLM service for structured generation

    Returns:
        List of field names to display (5-7 fields)
    """
    # Get available fields (excluding internal/qualification fields)
    available_fields = [f.name for f in table.fields if f.category != FieldCategory.QUALIFICATION]

    # If we have 7 or fewer fields, just return them all
    if len(available_fields) <= MAX_DISPLAY_FIELDS:
        return available_fields

    # Build context for LLM
    requirements_context = ""
    if user_requirements:
        product_type = user_requirements.get("product_type", "product")
        must_haves = user_requirements.get("must_haves", [])
        priorities = user_requirements.get("priorities", [])
        nice_to_haves = user_requirements.get("nice_to_haves", [])

        requirements_context = f"""
Product type: {product_type}
Must-haves: {", ".join(must_haves) if must_haves else "None specified"}
Priorities: {", ".join(priorities) if priorities else "None specified"}
Nice-to-haves: {", ".join(nice_to_haves) if nice_to_haves else "None specified"}
"""

    prompt = f"""Select the {MIN_DISPLAY_FIELDS}-{MAX_DISPLAY_FIELDS} most important fields to display in a compact product comparison table.

User Requirements:
{requirements_context}

Available fields: {", ".join(available_fields)}

Selection criteria:
1. Always include "price" if available (users almost always care about price)
2. Include fields that directly address the user's must-haves and priorities
3. Include fields that differentiate products meaningfully
4. Prefer quantitative fields (specs, measurements) over descriptive text
5. Avoid redundant fields that show similar information
6. Prefer fields with short values (prices, ratings, specs) over long text descriptions

Return exactly {MIN_DISPLAY_FIELDS}-{MAX_DISPLAY_FIELDS} field names from the available list."""

    try:
        result = await llm_service.generate_structured(
            messages=[HumanMessage(content=prompt)],
            schema=SelectedFields,
        )

        # Validate returned fields exist
        valid_fields = [f for f in result.fields if f in available_fields]

        if len(valid_fields) < MIN_DISPLAY_FIELDS:
            # Fall back to first N fields if LLM selection is insufficient
            logger.warning(
                f"LLM field selection returned only {len(valid_fields)} valid fields, "
                f"falling back to default selection"
            )
            return available_fields[:MAX_DISPLAY_FIELDS]

        logger.info(f"LLM selected fields: {valid_fields} ({result.reasoning})")
        return valid_fields[:MAX_DISPLAY_FIELDS]

    except Exception as e:
        logger.warning(f"LLM field selection failed: {e}, using default fields")
        # Fall back to first N fields
        return available_fields[:MAX_DISPLAY_FIELDS]


def _get_field_type_hint(field_name: str, sample_values: list[Any]) -> str:
    """
    Determine display type hint for a field based on name and sample values.

    Returns:
        'narrow' for compact fields (price, rating, numeric specs)
        'standard' for normal text fields
    """
    # Field names that are typically narrow
    narrow_patterns = [
        "price",
        "rating",
        "score",
        "weight",
        "count",
        "size",
        "capacity",
        "power",
        "speed",
        "year",
        "warranty",
    ]

    field_lower = field_name.lower()

    # Check if field name matches narrow patterns
    for pattern in narrow_patterns:
        if pattern in field_lower:
            return "narrow"

    # Check sample values - if most are short, treat as narrow
    if sample_values:
        non_null_values = [v for v in sample_values if v is not None]
        if non_null_values:
            avg_length = sum(len(str(v)) for v in non_null_values) / len(non_null_values)
            if avg_length <= 15:
                return "narrow"

    return "standard"


def build_product_table_props(
    table: ComparisonTable,
    selected_row_ids: list[str],
    selected_fields: list[str],
    user_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build props dict for the ProductTable React component.

    Args:
        table: The comparison table with all data
        selected_row_ids: List of row_ids to include
        selected_fields: List of field names to display
        user_requirements: User requirements for product type context

    Returns:
        Props dict matching ProductTable component interface
    """
    # Build field labels from field definitions
    field_labels = {}
    for field in table.fields:
        if field.name in selected_fields:
            # Convert snake_case to Title Case
            label = field.name.replace("_", " ").title()
            field_labels[field.name] = label

    # Collect sample values for each field to determine type hints
    field_sample_values: dict[str, list[Any]] = {f: [] for f in selected_fields}
    for row_id in selected_row_ids:
        row = table.rows.get(row_id)
        if row:
            for field_name in selected_fields:
                cell = row.cells.get(field_name)
                if cell and cell.value is not None:
                    field_sample_values[field_name].append(cell.value)

    # Determine field type hints for column sizing
    field_types = {}
    for field_name in selected_fields:
        field_types[field_name] = _get_field_type_hint(field_name, field_sample_values[field_name])

    # Build product list
    products = []
    for row_id in selected_row_ids:
        row = table.rows.get(row_id)
        if not row:
            continue

        # Build cells dict with value and status
        cells = {}
        for field_name in selected_fields:
            cell = row.cells.get(field_name)
            if cell:
                cells[field_name] = {
                    "value": cell.value,
                    "status": cell.status.value,  # Convert enum to string
                }
            else:
                cells[field_name] = {
                    "value": None,
                    "status": "pending",
                }

        products.append(
            {
                "id": row_id,
                "name": row.candidate.name,
                "url": row.candidate.official_url,
                "manufacturer": row.candidate.manufacturer,
                "cells": cells,
            }
        )

    # Get product type for footer text
    product_type = "products"
    if user_requirements and user_requirements.get("product_type"):
        product_type = user_requirements["product_type"] + "s"

    return {
        "products": products,
        "fields": selected_fields,
        "fieldLabels": field_labels,
        "fieldTypes": field_types,
        "totalProducts": len(table.rows),
        "productType": product_type,
    }


async def prepare_product_table_props(
    living_table_data: dict[str, Any] | None,
    user_requirements: dict[str, Any] | None,
    llm_service: LLMService,
) -> dict[str, Any] | None:
    """
    Prepare complete props for ProductTable React component.

    This is the main entry point that orchestrates:
    1. Validating and parsing the table data
    2. Selecting top products
    3. Selecting key fields via LLM
    4. Building the final props dict

    Args:
        living_table_data: Serialized ComparisonTable dict from state
        user_requirements: User requirements dict from state
        llm_service: LLM service for field selection

    Returns:
        Props dict ready for CustomElement, or None if no data
    """
    if not living_table_data:
        return None

    try:
        # Parse table data
        table = ComparisonTable.model_validate(living_table_data)

        if not table.rows:
            return None

        # Select top products
        selected_row_ids = select_top_products(table, max_count=MAX_DISPLAY_PRODUCTS)

        if not selected_row_ids:
            return None

        # Select key fields
        selected_fields = await select_key_fields(
            table=table,
            user_requirements=user_requirements,
            llm_service=llm_service,
        )

        if not selected_fields:
            return None

        # Build props
        props = build_product_table_props(
            table=table,
            selected_row_ids=selected_row_ids,
            selected_fields=selected_fields,
            user_requirements=user_requirements,
        )

        logger.info(
            f"Prepared ProductTable props: {len(props['products'])} products, "
            f"{len(props['fields'])} fields"
        )

        return props

    except Exception as e:
        logger.exception(f"Failed to prepare ProductTable props: {e}")
        return None
