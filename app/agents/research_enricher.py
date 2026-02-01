"""Enricher sub-step - Build comparison table via Lattice enrichment."""

from app.models.schemas.shortlist import CellStatus, ComparisonTable
from app.services.lattice import get_lattice_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


def meets_requirements(candidate: dict) -> bool:
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

    # Get cached Lattice service
    lattice_service = get_lattice_service()

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
            if meets_requirements(result.data):
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

    # Get cached Lattice service
    lattice_service = get_lattice_service()
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
