"""Living table management utilities for RESEARCH node."""

from app.models.schemas.shortlist import Candidate, ComparisonTable, FieldDefinition
from app.models.state import AgentState
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_or_create_living_table(state: AgentState) -> ComparisonTable:
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


def add_candidates_to_table(
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


def add_requested_fields_to_table(
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
