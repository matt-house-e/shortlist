"""Tests for the ComparisonTable and related schemas."""

import pytest

from app.models.schemas.shortlist import (
    Candidate,
    CellStatus,
    ComparisonTable,
    FieldDefinition,
    TableCell,
    TableRow,
)


class TestTableCell:
    """Tests for TableCell model."""

    def test_default_status_is_pending(self):
        """Cell should default to PENDING status."""
        cell = TableCell()
        assert cell.status == CellStatus.PENDING
        assert cell.value is None

    def test_cell_with_value(self):
        """Cell can be created with value and status."""
        cell = TableCell(
            value="test value",
            status=CellStatus.ENRICHED,
            source="lattice",
        )
        assert cell.value == "test value"
        assert cell.status == CellStatus.ENRICHED
        assert cell.source == "lattice"


class TestTableRow:
    """Tests for TableRow model."""

    def test_row_creation_with_candidate(self):
        """Row should be created with a candidate."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row = TableRow(candidate=candidate)

        assert row.candidate.name == "Test Product"
        assert row.row_id is not None
        assert len(row.cells) == 0

    def test_row_has_uuid(self):
        """Row should have a unique UUID."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row1 = TableRow(candidate=candidate)
        row2 = TableRow(candidate=candidate)

        assert row1.row_id != row2.row_id


class TestComparisonTable:
    """Tests for ComparisonTable model."""

    @pytest.fixture
    def empty_table(self) -> ComparisonTable:
        """Create an empty comparison table."""
        return ComparisonTable()

    @pytest.fixture
    def table_with_fields(self) -> ComparisonTable:
        """Create a table with standard fields."""
        table = ComparisonTable()
        table.add_field(
            FieldDefinition(
                name="name",
                prompt="Extract the product name",
                data_type="string",
                category="standard",
            )
        )
        table.add_field(
            FieldDefinition(
                name="price",
                prompt="Extract the product price",
                data_type="string",
                category="standard",
            )
        )
        return table

    def test_empty_table(self, empty_table: ComparisonTable):
        """Empty table should have no rows or fields."""
        assert len(empty_table.rows) == 0
        assert len(empty_table.fields) == 0
        assert empty_table.get_row_count() == 0

    def test_add_field(self, empty_table: ComparisonTable):
        """Adding a field should add to fields list."""
        field = FieldDefinition(
            name="test_field",
            prompt="Test prompt",
            data_type="string",
            category="standard",
        )
        empty_table.add_field(field)

        assert len(empty_table.fields) == 1
        assert empty_table.fields[0].name == "test_field"

    def test_add_field_no_duplicate(self, table_with_fields: ComparisonTable):
        """Adding a field with same name should not create duplicate."""
        initial_count = len(table_with_fields.fields)

        # Try to add a field with the same name
        table_with_fields.add_field(
            FieldDefinition(
                name="name",  # Already exists
                prompt="Different prompt",
                data_type="string",
                category="standard",
            )
        )

        assert len(table_with_fields.fields) == initial_count

    def test_add_row(self, table_with_fields: ComparisonTable):
        """Adding a row should create cells for all fields."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        assert row_id is not None
        assert table_with_fields.get_row_count() == 1

        row = table_with_fields.rows[row_id]
        assert len(row.cells) == 2  # name and price fields
        assert "name" in row.cells
        assert "price" in row.cells
        assert row.cells["name"].status == CellStatus.PENDING

    def test_add_row_deduplication(self, table_with_fields: ComparisonTable):
        """Adding a duplicate candidate should return None."""
        candidate1 = Candidate(name="Test Product", manufacturer="Test Brand")
        candidate2 = Candidate(name="Test Product", manufacturer="Different Brand")

        row_id1 = table_with_fields.add_row(candidate1)
        row_id2 = table_with_fields.add_row(candidate2)

        assert row_id1 is not None
        assert row_id2 is None  # Duplicate, not added
        assert table_with_fields.get_row_count() == 1

    def test_add_row_fuzzy_deduplication(self, table_with_fields: ComparisonTable):
        """Fuzzy name matching should detect similar products."""
        candidate1 = Candidate(name="Samsung Galaxy S21", manufacturer="Samsung")
        candidate2 = Candidate(name="Samsung Galaxy S21 Ultra", manufacturer="Samsung")

        row_id1 = table_with_fields.add_row(candidate1)
        row_id2 = table_with_fields.add_row(candidate2)

        # S21 is contained in "S21 Ultra", should be detected as duplicate
        assert row_id1 is not None
        assert row_id2 is None
        assert table_with_fields.get_row_count() == 1

    def test_has_candidate(self, table_with_fields: ComparisonTable):
        """has_candidate should return True for existing products."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        table_with_fields.add_row(candidate)

        assert table_with_fields.has_candidate("Test Product")
        assert table_with_fields.has_candidate("test product")  # Case insensitive
        assert table_with_fields.has_candidate("TEST PRODUCT")
        assert not table_with_fields.has_candidate("Different Product")

    def test_add_field_marks_existing_rows_pending(self, table_with_fields: ComparisonTable):
        """Adding a new field should mark all existing rows as PENDING for that field."""
        # Add a row first
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        # Add a new field
        table_with_fields.add_field(
            FieldDefinition(
                name="warranty",
                prompt="Extract warranty info",
                data_type="string",
                category="user_driven",
            )
        )

        # Check that the existing row has a PENDING cell for the new field
        row = table_with_fields.rows[row_id]
        assert "warranty" in row.cells
        assert row.cells["warranty"].status == CellStatus.PENDING

    def test_update_cell(self, table_with_fields: ComparisonTable):
        """update_cell should set value and status."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        table_with_fields.update_cell(
            row_id=row_id,
            field_name="price",
            value="$99.99",
            status=CellStatus.ENRICHED,
            source="lattice",
        )

        row = table_with_fields.rows[row_id]
        assert row.cells["price"].value == "$99.99"
        assert row.cells["price"].status == CellStatus.ENRICHED
        assert row.cells["price"].source == "lattice"

    def test_update_cell_meets_requirements(self, table_with_fields: ComparisonTable):
        """Updating meets_requirements field should update row.meets_requirements."""
        # Add qualification field
        table_with_fields.add_field(
            FieldDefinition(
                name="meets_requirements",
                prompt="Does this meet requirements?",
                data_type="boolean",
                category="qualification",
            )
        )

        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        # Update to TRUE
        table_with_fields.update_cell(
            row_id=row_id,
            field_name="meets_requirements",
            value=True,
            status=CellStatus.ENRICHED,
        )

        row = table_with_fields.rows[row_id]
        assert row.meets_requirements is True

    def test_get_pending_cells(self, table_with_fields: ComparisonTable):
        """get_pending_cells should return all cells needing enrichment."""
        candidate1 = Candidate(name="Product 1", manufacturer="Brand 1")
        candidate2 = Candidate(name="Product 2", manufacturer="Brand 2")
        row_id1 = table_with_fields.add_row(candidate1)
        table_with_fields.add_row(candidate2)

        # All cells should be pending initially
        pending = table_with_fields.get_pending_cells()
        assert len(pending) == 4  # 2 rows x 2 fields

        # Enrich one cell
        table_with_fields.update_cell(
            row_id=row_id1,
            field_name="name",
            value="Product 1",
            status=CellStatus.ENRICHED,
        )

        pending = table_with_fields.get_pending_cells()
        assert len(pending) == 3

    def test_get_field_names(self, table_with_fields: ComparisonTable):
        """get_field_names should return field names, excluding internal fields."""
        # Add a qualification field
        table_with_fields.add_field(
            FieldDefinition(
                name="meets_requirements",
                prompt="Does this meet requirements?",
                data_type="boolean",
                category="qualification",
            )
        )

        # Should exclude qualification by default
        names = table_with_fields.get_field_names(exclude_internal=True)
        assert "name" in names
        assert "price" in names
        assert "meets_requirements" not in names

        # Should include all when exclude_internal=False
        all_names = table_with_fields.get_field_names(exclude_internal=False)
        assert "meets_requirements" in all_names

    def test_to_markdown_empty_table(self, empty_table: ComparisonTable):
        """Empty table should return placeholder text."""
        markdown = empty_table.to_markdown()
        assert "*No products in table yet.*" in markdown

    def test_to_markdown_with_data(self, table_with_fields: ComparisonTable):
        """Table with data should render as markdown table."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        table_with_fields.update_cell(
            row_id=row_id,
            field_name="name",
            value="Test Product",
            status=CellStatus.ENRICHED,
        )
        table_with_fields.update_cell(
            row_id=row_id,
            field_name="price",
            value="$99.99",
            status=CellStatus.ENRICHED,
        )

        markdown = table_with_fields.to_markdown()
        assert "| name |" in markdown
        assert "| price |" in markdown
        assert "Test Product" in markdown
        assert "$99.99" in markdown

    def test_to_markdown_shows_pending(self, table_with_fields: ComparisonTable):
        """Pending cells should show status indicator."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        table_with_fields.add_row(candidate)

        markdown = table_with_fields.to_markdown(show_pending=True)
        assert "*(pending)*" in markdown

    def test_to_csv(self, table_with_fields: ComparisonTable):
        """Table should export to CSV format."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        table_with_fields.update_cell(
            row_id=row_id,
            field_name="name",
            value="Test Product",
            status=CellStatus.ENRICHED,
        )
        table_with_fields.update_cell(
            row_id=row_id,
            field_name="price",
            value="$99.99",
            status=CellStatus.ENRICHED,
        )

        csv_output = table_with_fields.to_csv()
        lines = csv_output.strip().split("\n")

        assert len(lines) == 2  # Header + 1 data row
        assert "name" in lines[0]
        assert "price" in lines[0]
        assert "Test Product" in lines[1]
        assert "$99.99" in lines[1]

    def test_get_qualified_rows(self, table_with_fields: ComparisonTable):
        """get_qualified_rows should return only rows meeting requirements."""
        # Add qualification field
        table_with_fields.add_field(
            FieldDefinition(
                name="meets_requirements",
                prompt="Does this meet requirements?",
                data_type="boolean",
                category="qualification",
            )
        )

        candidate1 = Candidate(name="Product 1", manufacturer="Brand 1")
        candidate2 = Candidate(name="Product 2", manufacturer="Brand 2")
        row_id1 = table_with_fields.add_row(candidate1)
        row_id2 = table_with_fields.add_row(candidate2)

        # Mark first as meeting requirements, second as not
        table_with_fields.update_cell(
            row_id=row_id1,
            field_name="meets_requirements",
            value=True,
            status=CellStatus.ENRICHED,
        )
        table_with_fields.update_cell(
            row_id=row_id2,
            field_name="meets_requirements",
            value=False,
            status=CellStatus.ENRICHED,
        )

        qualified = table_with_fields.get_qualified_rows()
        assert len(qualified) == 1
        assert qualified[0].candidate.name == "Product 1"

    def test_get_enrichment_progress(self, table_with_fields: ComparisonTable):
        """get_enrichment_progress should return correct counts."""
        candidate = Candidate(name="Test Product", manufacturer="Test Brand")
        row_id = table_with_fields.add_row(candidate)

        # Initially all pending
        enriched, total = table_with_fields.get_enrichment_progress()
        assert total == 2
        assert enriched == 0

        # Enrich one cell
        table_with_fields.update_cell(
            row_id=row_id,
            field_name="name",
            value="Test Product",
            status=CellStatus.ENRICHED,
        )

        enriched, total = table_with_fields.get_enrichment_progress()
        assert total == 2
        assert enriched == 1
