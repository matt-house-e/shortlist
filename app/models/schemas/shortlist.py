"""Shortlist domain-specific Pydantic schemas."""

import csv
import io
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.models.schemas.base import BaseSchema


class WorkflowPhase(str, Enum):
    """Workflow phase enumeration."""

    INTAKE = "intake"
    RESEARCH = "research"
    ADVISE = "advise"


# =============================================================================
# Cell-Level Tracking (Living Table)
# =============================================================================


class CellStatus(str, Enum):
    """Status of a table cell."""

    PENDING = "pending"  # Needs enrichment
    ENRICHED = "enriched"  # Successfully enriched
    FAILED = "failed"  # Enrichment failed
    FLAGGED = "flagged"  # User flagged for re-enrichment


class TableCell(BaseSchema):
    """A single cell in the comparison table with tracking metadata."""

    value: Any = None
    status: CellStatus = CellStatus.PENDING
    enriched_at: datetime | None = None
    source: str | None = None  # "lattice", "advisor", "user"
    error: str | None = None  # Error message if failed


class TableRow(BaseSchema):
    """A row in the comparison table representing a product candidate."""

    row_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate: "Candidate"
    cells: dict[str, TableCell] = Field(default_factory=dict)  # field_name -> cell
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    meets_requirements: bool | None = None
    source_query: str | None = None


class UserRequirements(BaseSchema):
    """User requirements for product search."""

    product_type: str = Field(..., description="Type of product the user is looking for")
    budget_min: float | None = Field(None, description="Minimum budget in USD", ge=0)
    budget_max: float | None = Field(None, description="Maximum budget in USD", ge=0)
    must_haves: list[str] = Field(
        default_factory=list,
        description="Required features or characteristics",
    )
    nice_to_haves: list[str] = Field(
        default_factory=list,
        description="Preferred but not required features",
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="Ordered list of user priorities (e.g., 'price', 'quality', 'brand')",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints or limitations (e.g., 'must ship to Canada', 'eco-friendly only')",
    )


class Candidate(BaseSchema):
    """Product candidate model."""

    name: str = Field(..., description="Product name")
    manufacturer: str = Field(..., description="Manufacturer or brand name")
    official_url: str | None = Field(None, description="Official product URL")
    description: str | None = Field(None, description="Product description")
    category: str | None = Field(None, description="Product category or type")


class FieldCategory(str, Enum):
    """Field category enumeration."""

    STANDARD = "standard"
    CATEGORY = "category"
    USER_DRIVEN = "user_driven"
    QUALIFICATION = "qualification"  # Internal fields for requirement matching


class DataType(str, Enum):
    """Data type enumeration for field definitions."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


class FieldDefinition(BaseSchema):
    """Definition for a comparison table field."""

    name: str = Field(..., description="Field name")
    prompt: str = Field(..., description="Prompt to use when extracting this field")
    data_type: DataType = Field(..., description="Expected data type for this field")
    category: FieldCategory = Field(
        ..., description="Field category (standard/category/user-driven)"
    )


class ComparisonTable(BaseSchema):
    """
    Living comparison table with cell-level tracking for incremental updates.

    This is the single source of truth for comparison data, supporting:
    - Incremental row addition with deduplication
    - Incremental field addition (marks existing rows PENDING)
    - Cell-level status tracking for efficient enrichment
    - Markdown and CSV export
    """

    fields: list[FieldDefinition] = Field(
        default_factory=list,
        description="Field definitions for the comparison table",
    )
    rows: dict[str, TableRow] = Field(
        default_factory=dict,
        description="Table rows keyed by row_id",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Legacy field for backwards compatibility during migration
    data: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="DEPRECATED: Use rows instead. Kept for migration.",
    )

    def _normalize_name(self, name: str) -> str:
        """Normalize product name for deduplication comparison."""
        return name.lower().strip().replace("-", " ").replace("_", " ")

    def has_candidate(self, name: str) -> bool:
        """
        Check if a candidate with similar name already exists.

        Args:
            name: Product name to check

        Returns:
            True if a similar candidate exists
        """
        normalized = self._normalize_name(name)
        for row in self.rows.values():
            existing_normalized = self._normalize_name(row.candidate.name)
            # Exact match or one contains the other
            if normalized == existing_normalized:
                return True
            if normalized in existing_normalized or existing_normalized in normalized:
                return True
        return False

    def add_row(
        self,
        candidate: "Candidate",
        source_query: str | None = None,
    ) -> str | None:
        """
        Add a new row if the candidate doesn't already exist.

        Args:
            candidate: Product candidate to add
            source_query: Query that discovered this candidate

        Returns:
            row_id if added, None if duplicate
        """
        if self.has_candidate(candidate.name):
            return None

        row_id = str(uuid.uuid4())
        row = TableRow(
            row_id=row_id,
            candidate=candidate,
            cells={},
            source_query=source_query,
        )

        # Initialize cells for all existing fields as PENDING
        for field in self.fields:
            row.cells[field.name] = TableCell(status=CellStatus.PENDING)

        self.rows[row_id] = row
        self.last_modified = datetime.now(UTC)
        return row_id

    def add_field(self, field: FieldDefinition) -> None:
        """
        Add a new field definition and mark all existing rows PENDING for this field.

        Args:
            field: Field definition to add
        """
        # Check if field already exists
        existing_names = {f.name for f in self.fields}
        if field.name in existing_names:
            return

        self.fields.append(field)

        # Mark all existing rows as PENDING for this new field
        for row in self.rows.values():
            row.cells[field.name] = TableCell(status=CellStatus.PENDING)

        self.last_modified = datetime.now(UTC)

    def update_cell(
        self,
        row_id: str,
        field_name: str,
        value: Any,
        status: CellStatus,
        source: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Update a specific cell value and status.

        Args:
            row_id: Row identifier
            field_name: Field name
            value: New cell value
            status: New cell status
            source: Source of the data (e.g., "lattice", "advisor")
            error: Error message if status is FAILED
        """
        if row_id not in self.rows:
            return

        row = self.rows[row_id]
        row.cells[field_name] = TableCell(
            value=value,
            status=status,
            enriched_at=datetime.now(UTC) if status == CellStatus.ENRICHED else None,
            source=source,
            error=error,
        )

        # Update meets_requirements if this is the qualification field
        if field_name == "meets_requirements" and status == CellStatus.ENRICHED:
            if value in [True, "TRUE", "True", "true", "Yes", "yes", "1"]:
                row.meets_requirements = True
            else:
                row.meets_requirements = False

        self.last_modified = datetime.now(UTC)

    def get_pending_cells(self) -> list[tuple[str, str]]:
        """
        Get all cells that need enrichment.

        Returns:
            List of (row_id, field_name) tuples for cells with PENDING or FLAGGED status
        """
        pending = []
        for row_id, row in self.rows.items():
            for field_name, cell in row.cells.items():
                if cell.status in [CellStatus.PENDING, CellStatus.FLAGGED]:
                    pending.append((row_id, field_name))
        return pending

    def get_field_names(self, exclude_internal: bool = True) -> list[str]:
        """
        Get list of field names.

        Args:
            exclude_internal: If True, excludes qualification fields

        Returns:
            List of field names
        """
        names = []
        for field in self.fields:
            if exclude_internal and field.category == "qualification":
                continue
            names.append(field.name)
        return names

    def to_markdown(
        self,
        max_rows: int = 10,
        show_pending: bool = True,
        exclude_internal: bool = True,
    ) -> str:
        """
        Render table as markdown.

        Args:
            max_rows: Maximum number of rows to display
            show_pending: If True, shows pending status indicators
            exclude_internal: If True, excludes qualification fields

        Returns:
            Markdown formatted table string
        """
        if not self.rows:
            return "*No products in table yet.*"

        # Get display fields
        field_names = self.get_field_names(exclude_internal=exclude_internal)
        if not field_names:
            return "*No fields defined.*"

        # Build header
        header = "| " + " | ".join(field_names) + " |"
        separator = "| " + " | ".join(["---"] * len(field_names)) + " |"

        # Build rows
        row_lines = []
        for i, row in enumerate(self.rows.values()):
            if i >= max_rows:
                break

            cells = []
            for field_name in field_names:
                cell = row.cells.get(field_name)
                if cell is None:
                    cells.append("—")
                elif cell.status == CellStatus.PENDING and show_pending:
                    cells.append("*(pending)*")
                elif cell.status == CellStatus.FAILED and show_pending:
                    cells.append("*(failed)*")
                elif cell.value is None:
                    cells.append("—")
                else:
                    # Truncate long values
                    val_str = str(cell.value)
                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    # Escape pipe characters
                    val_str = val_str.replace("|", "\\|")
                    cells.append(val_str)

            row_lines.append("| " + " | ".join(cells) + " |")

        # Add row count note if truncated
        total_rows = len(self.rows)
        table = "\n".join([header, separator] + row_lines)

        if total_rows > max_rows:
            table += (
                f"\n\n*Showing {max_rows} of {total_rows} products. Export to CSV for full table.*"
            )

        return table

    def to_csv(self, exclude_internal: bool = True) -> str:
        """
        Export table to CSV format.

        Args:
            exclude_internal: If True, excludes qualification fields

        Returns:
            CSV formatted string
        """
        field_names = self.get_field_names(exclude_internal=exclude_internal)
        if not field_names:
            return ""

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(field_names)

        # Data rows
        for row in self.rows.values():
            row_data = []
            for field_name in field_names:
                cell = row.cells.get(field_name)
                if cell is None or cell.value is None:
                    row_data.append("")
                else:
                    row_data.append(str(cell.value))
            writer.writerow(row_data)

        return output.getvalue()

    def get_qualified_rows(self) -> list[TableRow]:
        """Get rows that meet requirements."""
        return [row for row in self.rows.values() if row.meets_requirements is True]

    def get_row_count(self) -> int:
        """Get total number of rows."""
        return len(self.rows)

    def get_enrichment_progress(self) -> tuple[int, int]:
        """
        Get enrichment progress.

        Returns:
            Tuple of (enriched_cells, total_cells)
        """
        total = 0
        enriched = 0
        for row in self.rows.values():
            for cell in row.cells.values():
                total += 1
                if cell.status == CellStatus.ENRICHED:
                    enriched += 1
        return enriched, total


class RefinementTrigger(str, Enum):
    """Trigger type for refinement."""

    USER_REQUEST = "user_request"
    INSUFFICIENT_DATA = "insufficient_data"
    NEW_REQUIREMENTS = "new_requirements"
    FIELD_ADDITION = "field_addition"


class RefinementEntry(BaseSchema):
    """Entry tracking a refinement loop iteration."""

    loop_count: int = Field(..., description="Refinement loop iteration number", ge=1)
    what_changed: str = Field(..., description="Description of what changed in this iteration")
    trigger: RefinementTrigger = Field(..., description="What triggered this refinement")


class SearchAngle(str, Enum):
    """Search angle enumeration for diverse query types."""

    REVIEW_SITE = "REVIEW_SITE"
    REDDIT = "REDDIT"
    BRAND_CATALOG = "BRAND_CATALOG"
    COMPARISON = "COMPARISON"
    BUDGET = "BUDGET"
    PREMIUM = "PREMIUM"
    FEATURE_FOCUS = "FEATURE_FOCUS"
    USE_CASE = "USE_CASE"
    ALTERNATIVES = "ALTERNATIVES"
    REGIONAL = "REGIONAL"
    DEALS = "DEALS"
    AVOID = "AVOID"
    # Legacy angles for backwards compatibility
    REVIEW_SITES = "review_sites"
    COMMUNITY = "community"
    MARKETPLACE = "marketplace"
    AUTHORITY = "authority"


class SearchQuery(BaseSchema):
    """A single search query with its strategic angle."""

    query: str = Field(..., description="The search query string")
    angle: str = Field(
        ...,
        description="The search angle type (REVIEW_SITE, REDDIT, BRAND_CATALOG, etc.)",
    )
    expected_results: str = Field(
        default="",
        description="What products this query should find",
    )


class SearchQueryPlan(BaseSchema):
    """Plan for multiple search queries generated by LLM."""

    queries: list[SearchQuery] = Field(
        ...,
        description="10-15 diverse search queries",
        min_length=3,
        max_length=20,
    )
    strategy_notes: str = Field(..., description="Brief explanation of the search strategy")
    brands_covered: list[str] = Field(
        default_factory=list,
        description="Brands included in search queries",
    )
    sources_covered: list[str] = Field(
        default_factory=list,
        description="Source types covered (review sites, reddit, etc.)",
    )


class DiscoveredCandidate(BaseSchema):
    """A product candidate discovered via web search."""

    name: str = Field(..., description="Full product name")
    manufacturer: str = Field(..., description="Brand/manufacturer name")
    official_url: str | None = Field(None, description="URL to official product page")
    description: str = Field(..., description="Brief product description")


# Resolve forward references for TableRow.candidate
TableRow.model_rebuild()
