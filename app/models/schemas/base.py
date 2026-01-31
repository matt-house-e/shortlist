"""Base schema utilities for Pydantic models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """
    Base schema with common configuration.

    All domain schemas should inherit from this class to ensure
    consistent behavior across the application.
    """

    model_config = ConfigDict(
        # Use enum values instead of names in serialization
        use_enum_values=True,
        # Validate field defaults
        validate_default=True,
        # Allow population by field name or alias
        populate_by_name=True,
        # Serialize datetime as ISO format strings
        json_encoders={datetime: lambda v: v.isoformat()},
    )


class TimestampedSchema(BaseSchema):
    """Base schema with timestamp fields."""

    created_at: datetime | None = None
    updated_at: datetime | None = None


# =============================================================================
# Example Domain Schemas (Placeholders)
# =============================================================================
# TODO: Add your domain-specific schemas below
#
# Example:
#
# class ClassificationResult(BaseSchema):
#     """Result of a classification operation."""
#     category: str
#     confidence: float
#     reasoning: str | None = None
#
# class KnowledgeSearchResult(BaseSchema):
#     """Result from knowledge base search."""
#     content: str
#     source: str
#     relevance_score: float
