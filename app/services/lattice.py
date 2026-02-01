"""Lattice enrichment service - Bulk data enrichment for product candidates."""

import csv
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from lattice import EnrichmentConfig, FieldManager, TableEnricher
from lattice.chains import WebEnrichedLLMChain

from app.config.settings import get_settings
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

    Uses WebEnrichedLLMChain with Tavily for real-time web data.
    """

    CATEGORY_NAME = "shortlist_enrichment"

    def __init__(self):
        """Initialize LatticeService with WebEnrichedLLMChain."""
        settings = get_settings()

        # Create WebEnrichedLLMChain (with Tavily web search)
        self.chain = WebEnrichedLLMChain.create(
            api_key=settings.openai_api_key,
            tavily_api_key=settings.tavily_api_key,
            model=settings.lattice_model,
            temperature=settings.lattice_temperature,
            max_tokens=settings.lattice_max_tokens,
        )

        # Create enrichment config
        self.config = EnrichmentConfig(
            batch_size=settings.lattice_batch_size,
            max_workers=settings.lattice_max_workers,
            row_delay=settings.lattice_row_delay,
            enable_async=True,
            enable_checkpointing=settings.lattice_enable_checkpointing,
            checkpoint_interval=settings.lattice_checkpoint_interval,
            enable_retries=True,
            max_retries=settings.lattice_max_retries,
            retry_delay=2.0,
            enable_progress_bar=False,  # Disabled for server context
        )

        self._temp_csv_path: Path | None = None

        logger.info("LatticeService initialized with WebEnrichedLLMChain")

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
        Enrich candidates using real Lattice library.

        Args:
            candidates: List of product candidates with name, official_url, etc.
            field_definitions: Field definitions for enrichment

        Returns:
            List of EnrichmentResult objects (one per candidate)
        """
        logger.info(f"Starting enrichment for {len(candidates)} candidates")

        try:
            # Create FieldManager from dynamic field definitions
            field_manager = self._create_field_manager(field_definitions)

            # Convert candidates to DataFrame
            df = pd.DataFrame(candidates)
            if "name" not in df.columns:
                df["name"] = [f"candidate_{i}" for i in range(len(df))]

            # Create enricher
            enricher = TableEnricher(
                chain=self.chain,
                field_manager=field_manager,
                config=self.config,
            )

            # Enrich using async method
            enriched_df = await enricher.enrich_dataframe_async(
                df,
                category=self.CATEGORY_NAME,
                overwrite_fields=False,
                data_identifier="shortlist_enrichment",
            )

            # Convert results
            results = self._convert_results(enriched_df, candidates, field_definitions)

            successful = sum(1 for r in results if r.success)
            logger.info(f"Enrichment complete: {successful}/{len(results)} successful")

            return results

        except Exception as e:
            logger.exception(f"Enrichment failed: {e}")
            # Return error results for all candidates
            return [
                EnrichmentResult(
                    candidate_id=c.get("name", f"candidate_{i}"),
                    success=False,
                    error=str(e),
                )
                for i, c in enumerate(candidates)
            ]

        finally:
            self._cleanup()

    def _create_field_manager(self, field_definitions: list[FieldDefinition]) -> FieldManager:
        """
        Create FieldManager from dynamic field definitions via temp CSV.

        Args:
            field_definitions: List of FieldDefinition objects

        Returns:
            Configured FieldManager instance
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["Category", "Field", "Prompt", "Instructions", "Data_Type"],
            )
            writer.writeheader()

            for fd in field_definitions:
                writer.writerow(
                    {
                        "Category": self.CATEGORY_NAME,
                        "Field": fd.field,
                        "Prompt": fd.prompt,
                        "Instructions": "",
                        "Data_Type": self._normalize_type(fd.data_type),
                    }
                )

            self._temp_csv_path = Path(f.name)

        return FieldManager.from_csv(str(self._temp_csv_path))

    def _normalize_type(self, data_type: str) -> str:
        """
        Normalize data type to Lattice format.

        Args:
            data_type: Input data type string

        Returns:
            Normalized type string for Lattice
        """
        return {"string": "String", "number": "Number", "boolean": "Boolean"}.get(
            data_type.lower(), "String"
        )

    def _convert_results(
        self,
        df: pd.DataFrame,
        original: list[dict[str, Any]],
        field_definitions: list[FieldDefinition],
    ) -> list[EnrichmentResult]:
        """
        Convert enriched DataFrame to list of EnrichmentResult.

        Args:
            df: Enriched DataFrame from Lattice
            original: Original candidate list
            field_definitions: Field definitions used for enrichment

        Returns:
            List of EnrichmentResult objects
        """
        field_names = [fd.field for fd in field_definitions]
        results = []

        for idx, row in df.iterrows():
            candidate_data = original[idx].copy() if idx < len(original) else {}

            for field in field_names:
                if field in row and pd.notna(row[field]):
                    candidate_data[field] = row[field]

            results.append(
                EnrichmentResult(
                    candidate_id=candidate_data.get("name", f"candidate_{idx}"),
                    success=True,
                    data=candidate_data,
                )
            )

        return results

    def _cleanup(self):
        """Clean up temp files."""
        if self._temp_csv_path and self._temp_csv_path.exists():
            self._temp_csv_path.unlink()
            self._temp_csv_path = None
