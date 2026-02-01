"""Field generation service for dynamic category-specific comparison fields."""

from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load prompt configuration
PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"
FIELD_GEN_PATH = PROMPTS_DIR / "field_generation.yaml"


class GeneratedField(BaseModel):
    """A single generated field definition."""

    name: str = Field(description="snake_case field identifier")
    prompt: str = Field(description="Detailed extraction prompt for Lattice")
    data_type: str = Field(description="Data type: string, number, or boolean")
    rationale: str = Field(default="", description="Why this field is important")


class FieldGenerationPlan(BaseModel):
    """Complete plan of generated fields."""

    fields: list[GeneratedField] = Field(
        description="List of generated field definitions",
        min_length=5,
        max_length=10,
    )
    category_detected: str = Field(
        default="",
        description="The product category detected from requirements",
    )
    strategy_notes: str = Field(
        default="",
        description="Brief explanation of field selection strategy",
    )


class FieldGenerationService:
    """
    Service for generating category-specific comparison fields.

    Uses LLM's inherent domain knowledge to determine relevant comparison
    fields for any product type based on user requirements.
    """

    def __init__(self):
        """Initialize the field generation service."""
        self.config = self._load_config()
        logger.info("FieldGenerationService initialized")

    def _load_config(self) -> dict:
        """Load the field generation configuration."""
        try:
            with open(FIELD_GEN_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load field generation config: {e}")
            return {}

    def _build_context(self, requirements: dict) -> dict:
        """
        Build context for field generation from requirements.

        Args:
            requirements: User requirements dict

        Returns:
            Context dict for prompt template
        """
        product_type = requirements.get("product_type", "product")
        must_haves = requirements.get("must_haves", [])
        nice_to_haves = requirements.get("nice_to_haves", [])
        priorities = requirements.get("priorities", [])

        # Build budget constraint string
        budget_min = requirements.get("budget_min")
        budget_max = requirements.get("budget_max")
        if budget_min and budget_max:
            budget_constraint = f"${budget_min}-${budget_max}"
        elif budget_max:
            budget_constraint = f"Under ${budget_max}"
        elif budget_min:
            budget_constraint = f"Over ${budget_min}"
        else:
            budget_constraint = "No specific budget"

        return {
            "product_type": product_type,
            "must_haves": ", ".join(must_haves) if must_haves else "None specified",
            "nice_to_haves": ", ".join(nice_to_haves) if nice_to_haves else "None specified",
            "budget_constraint": budget_constraint,
            "priorities": ", ".join(priorities) if priorities else "None specified",
        }

    def _build_prompt(self, context: dict) -> str:
        """Build the user prompt from template and context."""
        template = self.config.get("user_prompt_template", "")
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"Missing template key: {e}")
            return template

    def _detect_fallback_category(self, product_type: str) -> str:
        """
        Detect which fallback category to use.

        Args:
            product_type: Product type from requirements

        Returns:
            Fallback category name
        """
        product_lower = product_type.lower()

        # Electronics keywords
        electronics_keywords = [
            "laptop",
            "phone",
            "tablet",
            "computer",
            "monitor",
            "tv",
            "television",
            "camera",
            "headphone",
            "speaker",
            "smartwatch",
            "earbuds",
        ]

        # Appliances keywords
        appliance_keywords = [
            "kettle",
            "toaster",
            "microwave",
            "oven",
            "fridge",
            "refrigerator",
            "freezer",
            "dishwasher",
            "washer",
            "dryer",
            "vacuum",
            "blender",
            "mixer",
            "coffee",
            "air fryer",
            "slow cooker",
            "pressure cooker",
        ]

        # Vehicle keywords
        vehicle_keywords = [
            "car",
            "vehicle",
            "sedan",
            "suv",
            "truck",
            "motorcycle",
            "motorbike",
            "coupe",
            "convertible",
            "hatchback",
            "wagon",
            "sports car",
            "electric vehicle",
            "ev",
            "hybrid",
        ]

        for keyword in electronics_keywords:
            if keyword in product_lower:
                return "electronics"

        for keyword in appliance_keywords:
            if keyword in product_lower:
                return "appliances"

        for keyword in vehicle_keywords:
            if keyword in product_lower:
                return "vehicles"

        return "default"

    def _fallback_fields(self, requirements: dict) -> list[dict]:
        """
        Generate fallback fields when LLM generation fails.

        Uses predefined templates based on product category.

        Args:
            requirements: User requirements dict

        Returns:
            List of field definition dicts
        """
        product_type = requirements.get("product_type", "product")
        category = self._detect_fallback_category(product_type)

        fallback_templates = self.config.get("fallback_templates", {})
        template_fields = fallback_templates.get(category, fallback_templates.get("default", []))

        logger.info(
            f"Using fallback fields for category '{category}': {len(template_fields)} fields"
        )

        fields = []
        for field_template in template_fields:
            fields.append(
                {
                    "category": "category",
                    "name": field_template["name"],
                    "prompt": field_template["prompt"],
                    "data_type": field_template.get("data_type", "string"),
                }
            )

        # Add fields based on user's must-haves
        must_haves = requirements.get("must_haves", [])
        for must_have in must_haves[:3]:  # Limit to 3 extra fields
            field_name = must_have.lower().replace(" ", "_").replace("-", "_")
            # Skip if already exists
            if any(f["name"] == field_name for f in fields):
                continue
            fields.append(
                {
                    "category": "category",
                    "name": field_name,
                    "prompt": f"Determine if this product has {must_have}. "
                    f"Look for '{must_have}' or related features. "
                    f"Answer 'Yes' if present, 'No' if not mentioned.",
                    "data_type": "string",
                }
            )

        return fields[:10]  # Ensure max 10 fields

    async def generate_fields(
        self,
        requirements: dict,
        llm_service: LLMService,
    ) -> list[dict]:
        """
        Generate category-specific comparison fields.

        Uses LLM to determine appropriate fields based on the product type
        and user requirements. Falls back to predefined templates on error.

        Args:
            requirements: User requirements dict
            llm_service: LLM service for generation

        Returns:
            List of field definition dicts ready for Lattice enrichment
        """
        product_type = requirements.get("product_type", "product")
        logger.info(f"Generating comparison fields for: {product_type}")

        # Build context and prompts
        context = self._build_context(requirements)
        system_prompt = self.config.get("system_prompt", "")
        user_prompt = self._build_prompt(context)

        try:
            # Generate structured output
            result = await llm_service.generate_structured(
                messages=[HumanMessage(content=user_prompt)],
                schema=FieldGenerationPlan,
                system_prompt=system_prompt,
            )

            # Convert to field definition dicts
            fields = []
            for field in result.fields:
                fields.append(
                    {
                        "category": "category",
                        "name": field.name,
                        "prompt": field.prompt,
                        "data_type": field.data_type,
                    }
                )

            logger.info(
                f"Generated {len(fields)} category-specific fields: {[f['name'] for f in fields]}"
            )
            if result.strategy_notes:
                logger.info(f"Strategy: {result.strategy_notes}")

            return fields

        except Exception as e:
            logger.warning(f"Field generation failed, using fallback: {e}")
            return self._fallback_fields(requirements)


# Module-level instance for convenience
_service_instance: FieldGenerationService | None = None


def get_field_generation_service() -> FieldGenerationService:
    """Get or create the field generation service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = FieldGenerationService()
    return _service_instance
