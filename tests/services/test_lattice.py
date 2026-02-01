"""Tests for Lattice enrichment service."""

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.lattice import (
    EnrichmentResult,
    FieldDefinition,
    LatticeService,
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


@pytest.fixture
def mock_settings():
    """Create mock settings for LatticeService."""
    settings = MagicMock()
    settings.openai_api_key = "test-openai-key"
    settings.lattice_model = "o4-mini"
    settings.lattice_temperature = 0.2
    settings.lattice_max_tokens = 4000
    settings.lattice_batch_size = 20
    settings.lattice_max_workers = 30
    settings.lattice_row_delay = 0.1
    settings.lattice_enable_checkpointing = False
    settings.lattice_checkpoint_interval = 100
    settings.lattice_max_retries = 3
    settings.lattice_reasoning_effort = "medium"
    settings.lattice_use_reasoning = True
    return settings


@patch("app.services.lattice.get_settings")
@patch("app.services.lattice.OpenAIWebSearchChain")
def test_lattice_service_initialization(mock_chain_class, mock_get_settings, mock_settings):
    """Test LatticeService initialization."""
    mock_get_settings.return_value = mock_settings
    mock_chain_class.create.return_value = MagicMock()

    service = LatticeService()

    assert service.chain is not None
    assert service.config is not None
    mock_chain_class.create.assert_called_once_with(
        api_key="test-openai-key",
        model="o4-mini",
        temperature=0.2,
        max_tokens=4000,
        reasoning_effort="medium",
        use_reasoning=True,
    )


@patch("app.services.lattice.get_settings")
@patch("app.services.lattice.OpenAIWebSearchChain")
def test_prepare_field_definitions(mock_chain_class, mock_get_settings, mock_settings):
    """Test preparing field definitions."""
    mock_get_settings.return_value = mock_settings
    mock_chain_class.create.return_value = MagicMock()

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


@patch("app.services.lattice.get_settings")
@patch("app.services.lattice.OpenAIWebSearchChain")
def test_normalize_type(mock_chain_class, mock_get_settings, mock_settings):
    """Test data type normalization."""
    mock_get_settings.return_value = mock_settings
    mock_chain_class.create.return_value = MagicMock()

    service = LatticeService()

    assert service._normalize_type("string") == "String"
    assert service._normalize_type("STRING") == "String"
    assert service._normalize_type("number") == "Number"
    assert service._normalize_type("boolean") == "Boolean"
    assert service._normalize_type("unknown") == "String"


@patch("app.services.lattice.get_settings")
@patch("app.services.lattice.OpenAIWebSearchChain")
def test_convert_results(mock_chain_class, mock_get_settings, mock_settings):
    """Test conversion of enriched DataFrame to results."""
    mock_get_settings.return_value = mock_settings
    mock_chain_class.create.return_value = MagicMock()

    service = LatticeService()

    # Create test data
    df = pd.DataFrame(
        [
            {"name": "Product A", "price": "$50", "rating": "4.5"},
            {"name": "Product B", "price": "$75", "rating": "4.2"},
        ]
    )

    original = [
        {"name": "Product A", "official_url": "https://example.com/a"},
        {"name": "Product B", "official_url": "https://example.com/b"},
    ]

    field_definitions = [
        FieldDefinition("standard", "price", "Extract price", "string"),
        FieldDefinition("standard", "rating", "Extract rating", "string"),
    ]

    results = service._convert_results(df, original, field_definitions)

    assert len(results) == 2
    assert all(r.success for r in results)
    assert results[0].candidate_id == "Product A"
    assert results[0].data["price"] == "$50"
    assert results[0].data["official_url"] == "https://example.com/a"
    assert results[1].candidate_id == "Product B"
    assert results[1].data["rating"] == "4.2"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_lattice_service_real_enrichment():
    """Integration test for real Lattice enrichment.

    This test requires actual API keys and will make real API calls.
    Uses OpenAI web search for enrichment.
    Run with: pytest -m integration tests/services/test_lattice.py
    """
    service = LatticeService()

    candidates = [
        {
            "name": "Fellow Stagg EKG Electric Kettle",
            "official_url": "https://fellowproducts.com/products/stagg-ekg-electric-pour-over-kettle",
        },
    ]

    field_definitions = [
        FieldDefinition("standard", "price", "Extract the current retail price", "string"),
        FieldDefinition("standard", "description", "Extract a brief product description", "string"),
    ]

    results = await service.enrich_candidates(candidates, field_definitions)

    assert len(results) == 1
    assert results[0].candidate_id == "Fellow Stagg EKG Electric Kettle"
    # Results may succeed or fail depending on API availability,
    # but the structure should be correct
    assert isinstance(results[0].success, bool)
    assert isinstance(results[0].data, dict)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_reasoning_model_finds_manufacturer_url():
    """Integration test verifying reasoning model finds manufacturer URLs.

    This test checks that the reasoning model with agentic search finds
    official manufacturer URLs instead of review site URLs.

    Run with: pytest -m integration tests/services/test_lattice.py -k "manufacturer_url"
    """
    service = LatticeService()

    # Test with a product where review sites often appear first in search
    candidates = [
        {
            "name": "HP Pavilion Pro 14",
            "manufacturer": "HP",
        },
    ]

    field_definitions = [
        FieldDefinition(
            "standard",
            "official_url",
            "The official product page URL on the manufacturer's website",
            "string",
        ),
        FieldDefinition("standard", "price", "Extract the current retail price", "string"),
    ]

    results = await service.enrich_candidates(candidates, field_definitions)

    assert len(results) == 1
    result = results[0]

    # Check structure
    assert isinstance(result.success, bool)
    assert isinstance(result.data, dict)

    # If successful and URL was found, verify it's from manufacturer
    if result.success and result.data.get("official_url"):
        url = result.data["official_url"]
        # Should be from hp.com, not a review site or retailer
        assert "hp.com" in url.lower(), f"Expected hp.com URL, got: {url}"
        # Should NOT be from known bad domains
        bad_domains = ["amazon.com", "bestbuy.com", "digitaltrends.com", "techradar.com"]
        for bad_domain in bad_domains:
            assert bad_domain not in url.lower(), f"URL should not be from {bad_domain}: {url}"
