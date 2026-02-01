"""Search strategy service for generating diverse product search queries."""

import json
from datetime import datetime
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.services.llm import LLMService
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Load knowledge bases
DATA_DIR = Path(__file__).parent.parent / "data"
PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"

CATEGORIES_PATH = DATA_DIR / "product_categories.yaml"
STRATEGY_PATH = PROMPTS_DIR / "search_strategy.yaml"


class SearchQuery(BaseModel):
    """A single search query with metadata."""

    query: str = Field(description="The search query text")
    angle: str = Field(description="Type of search angle")
    expected_results: str = Field(default="", description="What products this query should find")


class SearchQueryPlan(BaseModel):
    """Complete search plan with multiple queries."""

    queries: list[SearchQuery] = Field(
        description="List of diverse search queries", min_length=8, max_length=15
    )
    strategy_notes: str = Field(description="Explanation of search strategy")
    brands_covered: list[str] = Field(default_factory=list)
    sources_covered: list[str] = Field(default_factory=list)


class SearchStrategyService:
    """
    Service for generating diverse product search queries.

    Uses a knowledge base of product categories mapped to:
    - Authoritative review sites
    - Reddit communities
    - Top brands
    - Common specs and use cases
    """

    def __init__(self):
        """Initialize the search strategy service."""
        self.categories = self._load_categories()
        self.strategy_config = self._load_strategy()
        logger.info(
            f"SearchStrategyService initialized with {len(self.categories.get('categories', {}))} categories"
        )

    def _load_categories(self) -> dict:
        """Load the product categories knowledge base."""
        try:
            with open(CATEGORIES_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load categories: {e}")
            return {"categories": {}, "query_templates": {}, "regions": {}}

    def _load_strategy(self) -> dict:
        """Load the search strategy configuration."""
        try:
            with open(STRATEGY_PATH) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load strategy config: {e}")
            return {}

    def _find_category(self, product_type: str) -> tuple[str, dict]:
        """
        Find the matching category for a product type.

        Args:
            product_type: The product type from requirements

        Returns:
            Tuple of (category_name, category_config)
        """
        product_lower = product_type.lower()
        categories = self.categories.get("categories", {})

        # Direct match
        if product_lower in categories:
            return product_lower, categories[product_lower]

        # Check aliases
        for cat_name, cat_config in categories.items():
            aliases = cat_config.get("aliases", [])
            for alias in aliases:
                if alias.lower() in product_lower or product_lower in alias.lower():
                    logger.info(f"Matched '{product_type}' to category '{cat_name}'")
                    return cat_name, cat_config

        # Partial match on category name
        for cat_name, cat_config in categories.items():
            if cat_name in product_lower or product_lower in cat_name:
                return cat_name, cat_config

        # Default fallback
        logger.warning(f"No category match for '{product_type}', using default")
        return "default", categories.get("default", {})

    def _detect_region(self, requirements: dict) -> dict:
        """Detect region from requirements (currency, etc.)."""
        currency = requirements.get("currency", "").upper()
        regions = self.categories.get("regions", {})

        if currency in ["£", "GBP"]:
            return regions.get("uk", {})
        elif currency in ["$", "USD"]:
            return regions.get("us", {})

        # Default to UK
        return regions.get("uk", {})

    def _build_context(self, requirements: dict) -> dict:
        """
        Build the full context for query generation.

        Args:
            requirements: User requirements dict

        Returns:
            Context dict with category info, region, etc.
        """
        product_type = requirements.get("product_type", "product")
        category_name, category_config = self._find_category(product_type)
        region_config = self._detect_region(requirements)

        # Get price tiers
        price_tiers = category_config.get("price_tiers", {})
        budget_max = requirements.get("budget_max")

        # Determine price tier
        budget_tier = price_tiers.get("budget", 50)
        mid_tier = price_tiers.get("mid", 150)

        context = {
            "product_type": product_type,
            "category_name": category_name,
            "top_brands": category_config.get("top_brands", [])[:10],
            "review_sites": category_config.get("review_sites", [])[:6],
            "subreddits": category_config.get("subreddits", [])[:5],
            "key_specs": category_config.get("key_specs", []),
            "use_cases": category_config.get("use_cases", []),
            "budget_price": budget_tier,
            "mid_price": mid_tier,
            "currency": region_config.get("currency", "£"),
            "region": region_config.get("search_suffix", "UK"),
            "year": datetime.now().year,
            "must_haves": requirements.get("must_haves", []),
            "nice_to_haves": requirements.get("nice_to_haves", []),
            "specifications": requirements.get("specifications", []),
            "constraints": requirements.get("constraints", []),
            "budget_constraint": f"{region_config.get('currency', '£')}{budget_max}"
            if budget_max
            else "No specific budget",
            "priorities": requirements.get("priorities", []),
            "requirements_json": json.dumps(requirements, indent=2),
        }

        return context

    def _build_prompt(self, context: dict) -> str:
        """Build the user prompt from template and context."""
        template = self.strategy_config.get("user_prompt_template", "")

        # Format lists for readability
        formatted_context = context.copy()
        for key in [
            "top_brands",
            "review_sites",
            "subreddits",
            "key_specs",
            "use_cases",
            "must_haves",
            "nice_to_haves",
            "specifications",
            "constraints",
            "priorities",
        ]:
            if isinstance(formatted_context.get(key), list):
                formatted_context[key] = ", ".join(formatted_context[key]) or "None specified"

        try:
            return template.format(**formatted_context)
        except KeyError as e:
            logger.warning(f"Missing template key: {e}")
            return template

    async def generate_queries(
        self,
        requirements: dict,
        llm_service: LLMService,
    ) -> SearchQueryPlan:
        """
        Generate diverse search queries for the given requirements.

        Args:
            requirements: User requirements dict
            llm_service: LLM service for generation

        Returns:
            SearchQueryPlan with 10-15 diverse queries
        """
        product_type = requirements.get("product_type", "product")
        logger.info(f"Generating search queries for: {product_type}")

        # Build context
        context = self._build_context(requirements)
        logger.debug(f"Category context: {context['category_name']}")
        logger.debug(f"Top brands: {context['top_brands']}")

        # Build prompts
        system_prompt = self.strategy_config.get("system_prompt", "")
        user_prompt = self._build_prompt(context)

        try:
            # Generate structured output
            result = await llm_service.generate_structured(
                messages=[HumanMessage(content=user_prompt)],
                schema=SearchQueryPlan,
                system_prompt=system_prompt,
            )

            # Log summary
            angles = [q.angle for q in result.queries]
            angle_counts = {a: angles.count(a) for a in set(angles)}
            logger.info(f"Generated {len(result.queries)} queries: {angle_counts}")
            logger.info(f"Brands covered: {result.brands_covered}")
            logger.info(f"Strategy: {result.strategy_notes}")

            # Validate diversity
            self._validate_diversity(result)

            return result

        except Exception as e:
            logger.warning(f"Query generation failed, using fallback: {e}")
            return self._fallback_queries(requirements, context)

    def _validate_diversity(self, plan: SearchQueryPlan) -> None:
        """Log warnings if query plan lacks diversity."""
        angles = [q.angle for q in plan.queries]

        required_angles = ["REVIEW_SITE", "REDDIT", "BRAND_CATALOG", "COMPARISON"]
        missing = [a for a in required_angles if a not in angles]

        if missing:
            logger.warning(f"Missing required angles: {missing}")

        if len(plan.brands_covered) < 3:
            logger.warning(f"Low brand diversity: only {len(plan.brands_covered)} brands")

    def _fallback_queries(self, requirements: dict, context: dict) -> SearchQueryPlan:
        """Generate fallback queries when LLM generation fails."""
        product_type = requirements.get("product_type", "product")
        budget_max = requirements.get("budget_max")
        currency = context.get("currency", "£")
        year = context.get("year", 2025)
        brands = context.get("top_brands", [])[:4]
        review_sites = context.get("review_sites", ["wirecutter.com"])[:2]
        subreddits = context.get("subreddits", ["r/BuyItForLife"])[:2]

        queries = [
            SearchQuery(
                query=f"best {product_type} {year} site:{review_sites[0]}",
                angle="REVIEW_SITE",
                expected_results="Professional reviews",
            ),
            SearchQuery(
                query=f"{product_type} recommendations {subreddits[0]} {year}",
                angle="REDDIT",
                expected_results="Community recommendations",
            ),
            SearchQuery(
                query=f"best {product_type} comparison vs {year}",
                angle="COMPARISON",
                expected_results="Product comparisons",
            ),
            SearchQuery(
                query=f"best budget {product_type} under {currency}{budget_max or 100} {year}",
                angle="BUDGET",
                expected_results="Budget options",
            ),
            SearchQuery(
                query=f"{product_type} alternatives underrated {year}",
                angle="ALTERNATIVES",
                expected_results="Hidden gems",
            ),
        ]

        # Add brand queries
        for brand in brands[:3]:
            queries.append(
                SearchQuery(
                    query=f"{brand} {product_type} {year}",
                    angle="BRAND_CATALOG",
                    expected_results=f"Products from {brand}",
                )
            )

        return SearchQueryPlan(
            queries=queries,
            strategy_notes="Fallback queries due to generation error",
            brands_covered=brands[:3],
            sources_covered=["review sites", "reddit", "brand sites"],
        )


# Module-level instance for convenience
_service_instance = None


def get_search_strategy_service() -> SearchStrategyService:
    """Get or create the search strategy service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SearchStrategyService()
    return _service_instance
