"""Field generation service tests."""

import pytest


def test_field_generation_service_init():
    """Test FieldGenerationService initialization."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    assert service.config is not None


def test_get_field_generation_service_singleton():
    """Test that get_field_generation_service returns same instance."""
    from app.services.field_generation import get_field_generation_service

    service1 = get_field_generation_service()
    service2 = get_field_generation_service()
    assert service1 is service2


def test_build_context_full_requirements():
    """Test context building with full requirements."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "electric kettle",
        "budget_min": 30,
        "budget_max": 100,
        "must_haves": ["temperature control", "quiet operation"],
        "nice_to_haves": ["keep warm function"],
        "priorities": ["quality", "price"],
    }

    context = service._build_context(requirements)

    assert context["product_type"] == "electric kettle"
    assert context["budget_constraint"] == "$30-$100"
    assert "temperature control" in context["must_haves"]
    assert "quiet operation" in context["must_haves"]
    assert "keep warm function" in context["nice_to_haves"]
    assert "quality" in context["priorities"]


def test_build_context_minimal_requirements():
    """Test context building with minimal requirements."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "laptop",
    }

    context = service._build_context(requirements)

    assert context["product_type"] == "laptop"
    assert context["budget_constraint"] == "No specific budget"
    assert context["must_haves"] == "None specified"
    assert context["nice_to_haves"] == "None specified"


def test_build_context_budget_max_only():
    """Test context building with only max budget."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "headphones",
        "budget_max": 200,
    }

    context = service._build_context(requirements)

    assert context["budget_constraint"] == "Under $200"


def test_build_context_budget_min_only():
    """Test context building with only min budget."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "camera",
        "budget_min": 500,
    }

    context = service._build_context(requirements)

    assert context["budget_constraint"] == "Over $500"


def test_detect_fallback_category_electronics():
    """Test fallback category detection for electronics."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()

    assert service._detect_fallback_category("laptop computer") == "electronics"
    assert service._detect_fallback_category("wireless headphones") == "electronics"
    assert service._detect_fallback_category("smart tv") == "electronics"
    assert service._detect_fallback_category("digital camera") == "electronics"


def test_detect_fallback_category_appliances():
    """Test fallback category detection for appliances."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()

    assert service._detect_fallback_category("electric kettle") == "appliances"
    assert service._detect_fallback_category("toaster oven") == "appliances"
    assert service._detect_fallback_category("robot vacuum") == "appliances"
    assert service._detect_fallback_category("coffee maker") == "appliances"


def test_detect_fallback_category_default():
    """Test fallback category detection for unknown products."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()

    assert service._detect_fallback_category("running shoes") == "default"
    assert service._detect_fallback_category("office chair") == "default"
    assert service._detect_fallback_category("backpack") == "default"


def test_fallback_fields_appliances():
    """Test fallback field generation for appliances."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "electric kettle",
        "must_haves": ["temperature control"],
    }

    fields = service._fallback_fields(requirements)

    # Should have appliance template fields plus must-have derived fields
    assert len(fields) >= 5
    assert len(fields) <= 10

    # Check field structure
    for field in fields:
        assert "name" in field
        assert "prompt" in field
        assert "category" in field
        assert "data_type" in field
        assert field["category"] == "category"

    # Check for appliance-specific fields
    field_names = [f["name"] for f in fields]
    # At minimum, should have some appliance fields
    assert any("capacity" in name or "power" in name or "noise" in name for name in field_names)


def test_fallback_fields_includes_must_haves():
    """Test that fallback fields include fields derived from must-haves."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "electric kettle",
        "must_haves": ["quiet operation", "fast boil"],
    }

    fields = service._fallback_fields(requirements)
    field_names = [f["name"] for f in fields]

    # Should include fields for must-haves (converted to snake_case)
    assert "quiet_operation" in field_names or "fast_boil" in field_names


def test_fallback_fields_max_limit():
    """Test that fallback fields respects max 10 fields."""
    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()
    requirements = {
        "product_type": "electric kettle",
        "must_haves": [
            "feature1",
            "feature2",
            "feature3",
            "feature4",
            "feature5",
            "feature6",
        ],
    }

    fields = service._fallback_fields(requirements)

    assert len(fields) <= 10


def test_generated_field_model():
    """Test GeneratedField Pydantic model."""
    from app.services.field_generation import GeneratedField

    field = GeneratedField(
        name="capacity_liters",
        prompt="Extract the water capacity in liters.",
        data_type="number",
        rationale="Key spec for kettles",
    )

    assert field.name == "capacity_liters"
    assert field.data_type == "number"
    assert field.rationale == "Key spec for kettles"


def test_field_generation_plan_model():
    """Test FieldGenerationPlan Pydantic model."""
    from app.services.field_generation import FieldGenerationPlan, GeneratedField

    fields = [
        GeneratedField(
            name=f"field_{i}",
            prompt=f"Extract field {i}",
            data_type="string",
        )
        for i in range(5)
    ]

    plan = FieldGenerationPlan(
        fields=fields,
        category_detected="appliances",
        strategy_notes="Focus on kitchen appliance specs",
    )

    assert len(plan.fields) == 5
    assert plan.category_detected == "appliances"


def test_field_generation_plan_validation():
    """Test FieldGenerationPlan validates field count."""
    from pydantic import ValidationError

    from app.services.field_generation import FieldGenerationPlan, GeneratedField

    # Too few fields (less than 5)
    with pytest.raises(ValidationError):
        FieldGenerationPlan(
            fields=[
                GeneratedField(name="f1", prompt="p1", data_type="string"),
                GeneratedField(name="f2", prompt="p2", data_type="string"),
            ],
        )

    # Too many fields (more than 10)
    with pytest.raises(ValidationError):
        FieldGenerationPlan(
            fields=[
                GeneratedField(name=f"f{i}", prompt=f"p{i}", data_type="string") for i in range(15)
            ],
        )


@pytest.mark.asyncio
async def test_generate_fields_fallback_on_error(mock_settings):
    """Test that generate_fields falls back gracefully on LLM error."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.field_generation import FieldGenerationService

    service = FieldGenerationService()

    # Mock LLM service that raises an error
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(side_effect=Exception("LLM error"))

    requirements = {
        "product_type": "electric kettle",
        "must_haves": ["temperature control"],
    }

    # Should fall back to template fields without raising
    fields = await service.generate_fields(requirements, mock_llm)

    assert len(fields) >= 5
    assert all(f["category"] == "category" for f in fields)
