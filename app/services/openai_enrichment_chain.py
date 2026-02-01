"""
OpenAI web search enrichment chain.

Uses OpenAI's built-in web_search tool for real-time web context during enrichment.
Supports reasoning models (o4-mini) for agentic multi-step search with open_page/find_in_page.
Extracts real URLs from citations and sources to prevent hallucination.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Known retailer domains that should not be used as official URLs
RETAILER_DOMAINS = {
    "amazon.com",
    "amazon.co.uk",
    "amazon.de",
    "amazon.fr",
    "amazon.ca",
    "bestbuy.com",
    "walmart.com",
    "target.com",
    "newegg.com",
    "bhphotovideo.com",
    "adorama.com",
    "costco.com",
    "ebay.com",
    "aliexpress.com",
}

# Known review site domains that should not be used as official URLs
REVIEW_SITE_DOMAINS = {
    "techradar.com",
    "tomsguide.com",
    "digitaltrends.com",
    "cnet.com",
    "theverge.com",
    "engadget.com",
    "pcmag.com",
    "wired.com",
    "nytimes.com",
    "wirecutter.com",
    "rtings.com",
    "tomshardware.com",
    "anandtech.com",
    "notebookcheck.net",
    "gsmarena.com",
    "dpreview.com",
}


@dataclass
class EnrichmentConfig:
    """Configuration for OpenAI web search enrichment."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 4000


class OpenAIWebSearchChain:
    """
    Enrichment chain using OpenAI Responses API with web search.

    Uses web_search tool to get real-time context and extracts real URLs from citations.
    Supports reasoning models (o4-mini) for agentic multi-step search.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 4000,
        reasoning_effort: Literal["low", "medium", "high"] = "medium",
        use_reasoning: bool = False,
    ):
        """
        Initialize the OpenAI web search chain.

        Args:
            api_key: OpenAI API key (uses settings if not provided)
            model: Model to use for enrichment
            temperature: Temperature for generation
            max_tokens: Maximum tokens for response
            reasoning_effort: Effort level for reasoning models (low/medium/high)
            use_reasoning: Whether to use reasoning mode (for o4-mini)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.use_reasoning = use_reasoning
        self.client = AsyncOpenAI(api_key=self.api_key)

        logger.info(
            f"OpenAIWebSearchChain initialized with model={model}, "
            f"use_reasoning={use_reasoning}, reasoning_effort={reasoning_effort}"
        )

    @classmethod
    def create(
        cls,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 4000,
        reasoning_effort: Literal["low", "medium", "high"] = "medium",
        use_reasoning: bool = False,
        **kwargs,  # Accept and ignore extra params for compatibility
    ) -> "OpenAIWebSearchChain":
        """
        Factory method for creating chain.

        Args:
            api_key: OpenAI API key
            model: Model to use
            temperature: Temperature for generation
            max_tokens: Maximum tokens
            reasoning_effort: Effort level for reasoning models
            use_reasoning: Whether to use reasoning mode
            **kwargs: Ignored for compatibility

        Returns:
            Configured OpenAIWebSearchChain instance
        """
        return cls(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            use_reasoning=use_reasoning,
        )

    def _build_search_query(self, row_data: dict[str, Any]) -> str:
        """
        Build a search query from row data.

        Args:
            row_data: Product data including name, manufacturer, etc.

        Returns:
            Search query string
        """
        name = row_data.get("name", "")
        manufacturer = row_data.get("manufacturer", "")

        # Build focused search query
        query_parts = []
        if manufacturer:
            query_parts.append(manufacturer)
        if name:
            query_parts.append(name)

        query = " ".join(query_parts)
        return f"{query} specifications reviews price" if query else "product information"

    def _build_system_prompt(self, fields: dict[str, Any]) -> str:
        """
        Build system prompt for field extraction (non-reasoning mode).

        Args:
            fields: Dictionary of field names to their specifications

        Returns:
            System prompt string
        """
        field_descriptions = []
        for field_name, field_spec in fields.items():
            prompt = field_spec.get("Prompt", field_spec.get("prompt", ""))
            data_type = field_spec.get("Data_Type", field_spec.get("data_type", "string"))
            field_descriptions.append(f"- {field_name} ({data_type}): {prompt}")

        fields_text = "\n".join(field_descriptions)

        return f"""You are a product data enrichment specialist. Extract the requested fields from web search results.

FIELDS TO EXTRACT:
{fields_text}

CRITICAL INSTRUCTIONS:
1. Search the web for the product and extract EXACT values from the search results
2. For URLs: ONLY use URLs that appear in the citations/sources - NEVER generate or guess URLs
3. For prices: include currency symbol (e.g., "$29.99", "£49.99")
4. For ratings: include scale (e.g., "4.5/5", "8.5/10")
5. For boolean fields: return true or false
6. For missing data: return null

Return ONLY a valid JSON object with field names as keys. Example:
{{"name": "Product Name", "price": "$99.99", "rating": "4.5/5", "official_url": null}}"""

    def _build_reasoning_system_prompt(self, fields: dict[str, Any]) -> str:
        """
        Build system prompt for reasoning models with agentic search strategy.

        Reasoning models can use open_page and find_in_page actions for deeper research.

        Args:
            fields: Dictionary of field names to their specifications

        Returns:
            System prompt string for reasoning model
        """
        field_descriptions = []
        for field_name, field_spec in fields.items():
            prompt = field_spec.get("Prompt", field_spec.get("prompt", ""))
            data_type = field_spec.get("Data_Type", field_spec.get("data_type", "string"))
            field_descriptions.append(f"- {field_name} ({data_type}): {prompt}")

        fields_text = "\n".join(field_descriptions)

        return f"""You are a product data enrichment specialist with access to web search capabilities.

FIELDS TO EXTRACT:
{fields_text}

RESEARCH STRATEGY:
1. FIRST: Search for the official manufacturer product page (e.g., "HP Pavilion site:hp.com")
2. SECOND: If official page unavailable, search authoritative review sites
3. THIRD: Use open_page to access promising URLs and verify information
4. FOURTH: Use find_in_page to locate specific specifications on pages
5. VERIFY: Only include URLs you have actually visited and verified

CRITICAL URL RULES:
- For official_url: ONLY use manufacturer domains (e.g., hp.com, dell.com, apple.com, lenovo.com)
- NEVER use retailer URLs (amazon.com, bestbuy.com, walmart.com) for official_url
- NEVER use review site URLs (techradar.com, digitaltrends.com, wirecutter.com) for official_url
- If you cannot find a manufacturer URL, set official_url to null

DATA EXTRACTION RULES:
1. Extract EXACT values from the pages you visit
2. For prices: include currency symbol (e.g., "$29.99", "£49.99")
3. For ratings: include scale (e.g., "4.5/5", "8.5/10")
4. For boolean fields: return true or false
5. For missing data: return null

Return ONLY a valid JSON object with field names as keys. Example:
{{"name": "Product Name", "price": "$99.99", "rating": "4.5/5", "official_url": "https://manufacturer.com/product"}}"""

    def _build_user_prompt(self, row_data: dict[str, Any]) -> str:
        """
        Build user prompt with product context.

        Args:
            row_data: Product data

        Returns:
            User prompt string
        """
        # Format row data for context
        context_parts = []
        for key, value in row_data.items():
            if value and key not in ("_enrichment_status", "_last_enriched"):
                context_parts.append(f"{key}: {value}")

        context = "\n".join(context_parts)

        return f"""Search for this product and extract the requested fields:

PRODUCT INFORMATION:
{context}

Search the web for this product, then extract the requested fields from the search results.
Return ONLY the JSON object with the extracted values."""

    def _extract_json_from_response(self, content: str) -> dict[str, Any]:
        """
        Extract JSON object from LLM response.

        Args:
            content: Raw response content

        Returns:
            Parsed JSON dict or empty dict on failure
        """
        try:
            # Try direct JSON parse
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in response
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

        logger.warning(f"Failed to parse JSON from response: {content[:200]}...")
        return {}

    def _extract_urls_from_citations(self, citations: list) -> list[str]:
        """
        Extract URLs from citation annotations.

        Args:
            citations: List of citation objects

        Returns:
            List of URLs
        """
        urls = []
        for citation in citations:
            if hasattr(citation, "url") and citation.url:
                urls.append(citation.url)
        return urls

    def _extract_sources_from_response(self, response: Any) -> list[str]:
        """
        Extract ALL source URLs from web_search_call actions in the response.

        This captures all URLs the reasoning model visited, not just cited ones.

        Args:
            response: OpenAI API response object

        Returns:
            List of all source URLs from web search actions
        """
        sources = []

        if not response.output:
            return sources

        for item in response.output:
            # Check for web_search_call items
            if hasattr(item, "type") and item.type == "web_search_call":
                # Extract sources from the action
                if hasattr(item, "action") and item.action:
                    action = item.action
                    if hasattr(action, "sources") and action.sources:
                        for source in action.sources:
                            if hasattr(source, "url") and source.url:
                                sources.append(source.url)

        return sources

    def _get_domain(self, url: str) -> str:
        """
        Extract the domain from a URL.

        Args:
            url: Full URL string

        Returns:
            Domain string (e.g., "hp.com")
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _is_manufacturer_url(self, url: str, manufacturer: str) -> bool:
        """
        Check if a URL is from the manufacturer's domain.

        Args:
            url: URL to check
            manufacturer: Manufacturer name

        Returns:
            True if URL appears to be from manufacturer
        """
        if not url or not manufacturer:
            return False

        domain = self._get_domain(url)

        # Check if domain is a retailer or review site
        if domain in RETAILER_DOMAINS or domain in REVIEW_SITE_DOMAINS:
            return False

        # Check if manufacturer name is in domain
        manufacturer_lower = manufacturer.lower().replace(" ", "")
        # Handle common manufacturer domain patterns
        manufacturer_variants = [
            manufacturer_lower,
            manufacturer_lower.replace("-", ""),
            manufacturer_lower.split()[0] if " " in manufacturer else manufacturer_lower,
        ]

        for variant in manufacturer_variants:
            if variant in domain:
                return True

        return False

    def _validate_and_fix_urls(
        self,
        extracted: dict[str, Any],
        row_data: dict[str, Any],
        citation_urls: list[str],
        source_urls: list[str],
    ) -> dict[str, Any]:
        """
        Validate and fix URLs in extracted data.

        Ensures official_url is from manufacturer, not retailers or review sites.

        Args:
            extracted: Extracted field values
            row_data: Original product data
            citation_urls: URLs from citations
            source_urls: URLs from web_search_call sources

        Returns:
            Extracted data with fixed URLs
        """
        if "official_url" not in extracted:
            return extracted

        url = extracted.get("official_url")
        manufacturer = row_data.get("manufacturer", "")
        all_urls = list(set(citation_urls + source_urls))

        # If no URL or null, try to find one from sources
        if not url:
            best_url = self._find_manufacturer_url(all_urls, manufacturer)
            if best_url:
                extracted["official_url"] = best_url
                logger.debug(f"Found manufacturer URL from sources: {best_url}")
            return extracted

        # Check if URL is valid (in sources and from manufacturer)
        domain = self._get_domain(url)

        # If URL is from a retailer or review site, replace it
        if domain in RETAILER_DOMAINS or domain in REVIEW_SITE_DOMAINS:
            logger.debug(f"Replacing non-manufacturer URL: {url}")
            best_url = self._find_manufacturer_url(all_urls, manufacturer)
            if best_url:
                extracted["official_url"] = best_url
                logger.debug(f"Replaced with manufacturer URL: {best_url}")
            else:
                extracted["official_url"] = None
                logger.debug("No manufacturer URL found, setting to null")
            return extracted

        # If URL is not in any sources, it may be hallucinated
        if url not in all_urls:
            # Check if it looks like a valid manufacturer URL
            if self._is_manufacturer_url(url, manufacturer):
                # Keep it but log warning
                logger.debug(f"URL not in sources but appears valid: {url}")
            else:
                # Replace with manufacturer URL from sources
                best_url = self._find_manufacturer_url(all_urls, manufacturer)
                if best_url:
                    extracted["official_url"] = best_url
                    logger.debug(f"Replaced hallucinated URL with: {best_url}")
                else:
                    extracted["official_url"] = None
                    logger.debug("Hallucinated URL replaced with null")

        return extracted

    def _find_manufacturer_url(self, urls: list[str], manufacturer: str) -> str | None:
        """
        Find the best manufacturer URL from a list.

        Args:
            urls: List of URLs to search
            manufacturer: Manufacturer name

        Returns:
            Best manufacturer URL or None
        """
        for url in urls:
            if self._is_manufacturer_url(url, manufacturer):
                return url
        return None

    async def ainvoke(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Asynchronously process a row with web search enrichment.

        Args:
            input_data: Dictionary with 'row_data' and 'fields'

        Returns:
            Dictionary with 'output' key containing extracted field values
        """
        row_data = input_data.get("row_data", {})
        fields = input_data.get("fields", {})

        if not fields:
            return {"output": {}}

        try:
            # Build prompts - use reasoning prompt if enabled
            if self.use_reasoning:
                system_prompt = self._build_reasoning_system_prompt(fields)
            else:
                system_prompt = self._build_system_prompt(fields)
            user_prompt = self._build_user_prompt(row_data)

            # Build request kwargs
            request_kwargs: dict[str, Any] = {
                "model": self.model,
                "instructions": system_prompt,
                "input": [{"role": "user", "content": user_prompt}],
                "tools": [{"type": "web_search"}],
                "max_output_tokens": self.max_tokens,
            }

            # Add reasoning config for reasoning models
            if self.use_reasoning:
                request_kwargs["reasoning"] = {"effort": self.reasoning_effort}
                # Include web_search_call sources to get all visited URLs
                request_kwargs["include"] = ["web_search_call.action.sources"]
            else:
                request_kwargs["temperature"] = self.temperature

            # Call OpenAI Responses API with web search
            response = await self.client.responses.create(**request_kwargs)

            # Extract content and citations
            content = ""
            citations = []

            if response.output:
                for item in response.output:
                    if item.type == "message":
                        if item.content:
                            for content_item in item.content:
                                if content_item.type == "output_text":
                                    content = content_item.text or ""
                                    # Extract citations
                                    if (
                                        hasattr(content_item, "annotations")
                                        and content_item.annotations
                                    ):
                                        citations.extend(content_item.annotations)

            # Parse the JSON response
            extracted = self._extract_json_from_response(content)

            # Extract URLs from citations and sources
            citation_urls = self._extract_urls_from_citations(citations)
            source_urls = self._extract_sources_from_response(response)

            logger.debug(
                f"Found {len(citation_urls)} citation URLs, {len(source_urls)} source URLs"
            )

            # Validate and fix URLs
            if "official_url" in fields:
                extracted = self._validate_and_fix_urls(
                    extracted, row_data, citation_urls, source_urls
                )

            logger.debug(
                f"Enriched {row_data.get('name', 'unknown')}: "
                f"{len(extracted)} fields, {len(citations)} citations"
            )

            return {"output": extracted}

        except Exception as e:
            logger.error(f"OpenAI web search enrichment failed: {e}")
            return {"output": dict.fromkeys(fields, None)}

    def invoke(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Synchronous invoke (for compatibility).

        Args:
            input_data: Dictionary with 'row_data' and 'fields'

        Returns:
            Dictionary with 'output' key containing extracted field values
        """
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.ainvoke(input_data))
