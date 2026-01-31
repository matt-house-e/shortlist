"""Domain-specific Pydantic schemas."""

from app.models.schemas.base import BaseSchema
from app.models.schemas.shortlist import (
    Candidate,
    ComparisonTable,
    DataType,
    FieldCategory,
    FieldDefinition,
    RefinementEntry,
    RefinementTrigger,
    UserRequirements,
    WorkflowPhase,
)

__all__ = [
    "BaseSchema",
    "Candidate",
    "ComparisonTable",
    "DataType",
    "FieldCategory",
    "FieldDefinition",
    "RefinementEntry",
    "RefinementTrigger",
    "UserRequirements",
    "WorkflowPhase",
]
