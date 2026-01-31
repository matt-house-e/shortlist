"""Tests for Lattice enrichment service."""

import pytest

from app.services.lattice import (
    EnrichmentResult,
    FieldDefinition,
    LatticeService,
    MockLatticeService,
)


def test_field_definition_creation():
    """Test creating a field definition."""
    field_def = FieldDefinition(
        category="standard",
        field="price",
        prompt="Extract the product price",
        data_type="string",
    )

    assert field_def.category == "standard"
    assert field_def.field == "price"
    assert field_def.prompt == "Extract the product price"
    assert field_def.data_type == "string"


def test_field_definition_to_dict():
    """Test converting field definition to dictionary."""
    field_def = FieldDefinition(
        category="category",
        field="capacity",
        prompt="Extract capacity in liters",
        data_type="number",
    )

    result = field_def.to_dict()

    assert result == {
        "Category": "category",
        "Field": "capacity",
        "Prompt": "Extract capacity in liters",
        "Data_Type": "number",
    }


def test_enrichment_result_success():
    """Test successful enrichment result."""
    result = EnrichmentResult(
        candidate_id="product-1",
        success=True,
        data={"price": "$50", "rating": "4.5"},
    )

    assert result.candidate_id == "product-1"
    assert result.success is True
    assert result.data == {"price": "$50", "rating": "4.5"}
    assert result.error is None


def test_enrichment_result_failure():
    """Test failed enrichment result."""
    result = EnrichmentResult(
        candidate_id="product-2",
        success=False,
        error="Network timeout",
    )

    assert result.candidate_id == "product-2"
    assert result.success is False
    assert result.data == {}
    assert result.error == "Network timeout"


def test_lattice_service_initialization():
    """Test LatticeService initialization."""
    service = LatticeService(max_retries=3, batch_size=10)

    assert service.max_retries == 3
    assert service.batch_size == 10


def test_prepare_field_definitions():
    """Test preparing field definitions."""
    service = LatticeService()

    fields = [
        {
            "category": "standard",
            "name": "price",
            "prompt": "Extract price",
            "data_type": "string",
        },
        {
            "category": "category",
            "name": "capacity",
            "prompt": "Extract capacity",
            "data_type": "number",
        },
    ]

    field_defs = service.prepare_field_definitions(fields)

    assert len(field_defs) == 2
    assert field_defs[0].field == "price"
    assert field_defs[0].category == "standard"
    assert field_defs[1].field == "capacity"
    assert field_defs[1].data_type == "number"


@pytest.mark.asyncio
async def test_mock_lattice_service_enrichment():
    """Test mock enrichment service."""
    service = MockLatticeService()

    candidates = [
        {"name": "Product A", "official_url": "https://example.com/a"},
        {"name": "Product B", "official_url": "https://example.com/b"},
    ]

    field_defs = [
        FieldDefinition("standard", "price", "Extract price", "string"),
        FieldDefinition("standard", "rating", "Extract rating", "string"),
    ]

    results = await service.enrich_candidates(candidates, field_defs)

    assert len(results) == 2
    assert all(r.success for r in results)
    assert results[0].candidate_id == "Product A"
    assert results[1].candidate_id == "Product B"
    assert "price" in results[0].data
    assert "rating" in results[0].data


@pytest.mark.asyncio
async def test_lattice_service_batch_processing():
    """Test batch processing with small batch size."""
    service = MockLatticeService()
    service.batch_size = 1  # Force batching

    candidates = [
        {"name": "Product A", "official_url": "https://example.com/a"},
        {"name": "Product B", "official_url": "https://example.com/b"},
        {"name": "Product C", "official_url": "https://example.com/c"},
    ]

    field_defs = [
        FieldDefinition("standard", "price", "Extract price", "string"),
    ]

    results = await service.enrich_candidates(candidates, field_defs)

    assert len(results) == 3
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_enrichment_result_has_candidate_data():
    """Test that enrichment preserves candidate data."""
    service = MockLatticeService()

    candidates = [
        {
            "name": "Test Product",
            "official_url": "https://example.com/test",
            "manufacturer": "Test Brand",
        },
    ]

    field_defs = [
        FieldDefinition("standard", "price", "Extract price", "string"),
    ]

    results = await service.enrich_candidates(candidates, field_defs)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data["name"] == "Test Product"
    assert results[0].data["official_url"] == "https://example.com/test"
