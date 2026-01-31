"""Lattice enrichment service - Bulk data enrichment for product candidates."""

import asyncio
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


class FieldDefinition:
    """Field definition for Lattice enrichment."""

    def __init__(
        self,
        category: str,
        field: str,
        prompt: str,
        data_type: str,
    ):
        """
        Initialize field definition.

        Args:
            category: Field category (standard/category/user-driven)
            field: Field name
            prompt: Extraction prompt for Lattice
            data_type: Expected data type (string/number/boolean)
        """
        self.category = category
        self.field = field
        self.prompt = prompt
        self.data_type = data_type

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary format for Lattice CSV schema."""
        return {
            "Category": self.category,
            "Field": self.field,
            "Prompt": self.prompt,
            "Data_Type": self.data_type,
        }


class EnrichmentResult:
    """Result from enriching a single candidate."""

    def __init__(
        self,
        candidate_id: str,
        success: bool,
        data: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        """
        Initialize enrichment result.

        Args:
            candidate_id: Identifier for the candidate
            success: Whether enrichment succeeded
            data: Enriched data (if successful)
            error: Error message (if failed)
        """
        self.candidate_id = candidate_id
        self.success = success
        self.data = data or {}
        self.error = error


class LatticeService:
    """
    Service for bulk enrichment of product candidates using Lattice.

    Lattice extracts structured data from URLs using web-enriched chains.
    This service handles batch processing, retries, and error handling.
    """

    def __init__(self, max_retries: int = 2, batch_size: int = 20):
        """
        Initialize Lattice service.

        Args:
            max_retries: Maximum number of retries for failed enrichments
            batch_size: Maximum candidates per batch (for rate limiting)
        """
        self.max_retries = max_retries
        self.batch_size = batch_size
        logger.info(
            f"LatticeService initialized (max_retries={max_retries}, batch_size={batch_size})"
        )

    def prepare_field_definitions(
        self,
        fields: list[dict[str, Any]],
    ) -> list[FieldDefinition]:
        """
        Prepare field definitions in Lattice CSV schema format.

        Args:
            fields: List of field specifications with category, name, prompt, data_type

        Returns:
            List of FieldDefinition objects ready for Lattice
        """
        field_defs = []

        for field in fields:
            field_def = FieldDefinition(
                category=field.get("category", "standard"),
                field=field.get("name", ""),
                prompt=field.get("prompt", ""),
                data_type=field.get("data_type", "string"),
            )
            field_defs.append(field_def)

        logger.info(f"Prepared {len(field_defs)} field definitions")
        return field_defs

    async def enrich_candidates(
        self,
        candidates: list[dict[str, Any]],
        field_definitions: list[FieldDefinition],
    ) -> list[EnrichmentResult]:
        """
        Enrich candidates with structured data extraction.

        Processes candidates in batches, with retry logic and graceful error handling.

        Args:
            candidates: List of product candidates with name, official_url, etc.
            field_definitions: Field definitions for enrichment

        Returns:
            List of EnrichmentResult objects (one per candidate)
        """
        logger.info(f"Starting enrichment for {len(candidates)} candidates")

        # Split into batches if needed
        batches = [
            candidates[i : i + self.batch_size] for i in range(0, len(candidates), self.batch_size)
        ]

        results = []
        for batch_idx, batch in enumerate(batches):
            logger.info(
                f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} candidates)"
            )

            batch_results = await self._enrich_batch(batch, field_definitions)
            results.extend(batch_results)

        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        logger.info(f"Enrichment complete: {successful} successful, {failed} failed")

        return results

    async def _enrich_batch(
        self,
        candidates: list[dict[str, Any]],
        field_definitions: list[FieldDefinition],
    ) -> list[EnrichmentResult]:
        """
        Enrich a single batch of candidates.

        Args:
            candidates: Batch of candidates to enrich
            field_definitions: Field definitions for enrichment

        Returns:
            List of EnrichmentResult objects for this batch
        """
        results = []

        for candidate in candidates:
            result = await self._enrich_single_candidate(candidate, field_definitions)
            results.append(result)

        return results

    async def _enrich_single_candidate(
        self,
        candidate: dict[str, Any],
        field_definitions: list[FieldDefinition],
        retry_count: int = 0,
    ) -> EnrichmentResult:
        """
        Enrich a single candidate with retry logic.

        Args:
            candidate: Candidate to enrich
            field_definitions: Field definitions for enrichment
            retry_count: Current retry attempt

        Returns:
            EnrichmentResult for this candidate
        """
        candidate_id = candidate.get("name", "unknown")

        try:
            # TODO: Actual Lattice integration would go here
            # For now, this is a placeholder that would be replaced with:
            # enriched_data = await lattice_client.enrich(
            #     url=candidate["official_url"],
            #     fields=field_definitions,
            # )

            logger.info(f"Enriching candidate: {candidate_id}")

            # Placeholder: simulate enrichment
            enriched_data = await self._mock_enrich(candidate, field_definitions)

            return EnrichmentResult(
                candidate_id=candidate_id,
                success=True,
                data=enriched_data,
            )

        except Exception as e:
            logger.error(f"Enrichment failed for {candidate_id}: {e}")

            # Retry logic
            if retry_count < self.max_retries:
                logger.info(
                    f"Retrying {candidate_id} (attempt {retry_count + 1}/{self.max_retries})"
                )
                # Exponential backoff
                await asyncio.sleep(2**retry_count)
                return await self._enrich_single_candidate(
                    candidate,
                    field_definitions,
                    retry_count + 1,
                )

            # Max retries exceeded
            return EnrichmentResult(
                candidate_id=candidate_id,
                success=False,
                error=str(e),
            )

    async def _mock_enrich(
        self,
        candidate: dict[str, Any],
        field_definitions: list[FieldDefinition],
    ) -> dict[str, Any]:
        """
        Mock enrichment for testing.

        This simulates the Lattice API response structure.

        Args:
            candidate: Candidate to enrich
            field_definitions: Field definitions

        Returns:
            Enriched data dictionary
        """
        # Simulate API delay
        await asyncio.sleep(0.1)

        enriched_data = {
            "name": candidate.get("name"),
            "official_url": candidate.get("official_url"),
        }

        # Mock field values based on field definitions
        for field_def in field_definitions:
            if field_def.data_type == "number":
                enriched_data[field_def.field] = 4.5
            elif field_def.data_type == "boolean":
                enriched_data[field_def.field] = True
            else:
                enriched_data[field_def.field] = f"Mock {field_def.field}"

        return enriched_data


class MockLatticeService(LatticeService):
    """
    Mock Lattice service for testing.

    Always succeeds with predictable mock data.
    """

    def __init__(self):
        """Initialize mock service."""
        super().__init__(max_retries=0, batch_size=20)
        logger.info("MockLatticeService initialized")

    async def _mock_enrich(
        self,
        candidate: dict[str, Any],
        field_definitions: list[FieldDefinition],
    ) -> dict[str, Any]:
        """
        Mock enrichment with predictable test data.

        Args:
            candidate: Candidate to enrich
            field_definitions: Field definitions

        Returns:
            Enriched data dictionary
        """
        # No delay for tests
        return {
            "name": candidate.get("name"),
            "official_url": candidate.get("official_url"),
            "price": "$50",
            "rating": "4.5",
            "category": "test-category",
        }
