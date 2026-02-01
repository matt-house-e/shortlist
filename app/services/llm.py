"""LLM service abstraction layer."""

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import NamedTuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.config import Settings, get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMResponse(NamedTuple):
    """Response from an LLM call with metrics."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    response_time: float


@dataclass
class Citation:
    """A citation from web search results."""

    url: str
    title: str
    start_index: int
    end_index: int


@dataclass
class WebSearchConfig:
    """Configuration for web search."""

    enabled: bool = True
    allowed_domains: list[str] | None = None
    user_location: dict | None = None  # {country, city, region}


@dataclass
class WebSearchResponse:
    """Response from an LLM call with web search."""

    content: str
    citations: list[Citation] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    response_time: float = 0.0
    response_id: str | None = None  # For conversation continuity


class LLMService:
    """
    LLM service abstraction for provider-agnostic model interactions.

    Supports multiple providers:
    - OpenAI (gpt-4o, gpt-4-turbo, gpt-3.5-turbo, etc.)
    - Anthropic (claude-3-opus, claude-3-sonnet, etc.)
    - Mock (for testing)

    Usage:
        service = LLMService(settings)
        response = await service.generate(messages)
    """

    def __init__(self, settings: Settings):
        """
        Initialize LLM service with configuration.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self._client = None

        logger.info(f"LLM service initialized: {self.provider}/{self.model}")

    @property
    def client(self):
        """Lazy-load the LLM client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self):
        """Create the appropriate LLM client based on provider."""
        if self.provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                api_key=self.settings.openai_api_key,
            )

        elif self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=self.model,
                temperature=self.temperature,
                api_key=self.settings.anthropic_api_key,
            )

        elif self.provider == "mock":
            return MockLLMClient()

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def generate(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: Conversation history
            system_prompt: Optional system prompt to prepend

        Returns:
            LLMResponse with content and metrics
        """
        # Prepare messages with optional system prompt
        all_messages = []
        if system_prompt:
            all_messages.append(SystemMessage(content=system_prompt))
        all_messages.extend(messages)

        logger.debug(f"Generating response with {len(all_messages)} messages")

        try:
            start_time = time.perf_counter()
            response = await self.client.ainvoke(all_messages)
            response_time = time.perf_counter() - start_time

            # Extract token usage from response metadata
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = response.usage_metadata.get("input_tokens", 0)
                completion_tokens = response.usage_metadata.get("output_tokens", 0)
            elif hasattr(response, "response_metadata") and response.response_metadata:
                token_usage = response.response_metadata.get("token_usage", {})
                prompt_tokens = token_usage.get("prompt_tokens", 0)
                completion_tokens = token_usage.get("completion_tokens", 0)

            return LLMResponse(
                content=response.content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                response_time=response_time,
            )

        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise

    async def generate_structured(
        self,
        messages: list[BaseMessage],
        schema: type,
        system_prompt: str | None = None,
    ):
        """
        Generate a structured response matching the given schema.

        Args:
            messages: Conversation history
            schema: Pydantic model class for structured output
            system_prompt: Optional system prompt

        Returns:
            Instance of the schema class
        """
        # Prepare messages
        all_messages = []
        if system_prompt:
            all_messages.append(SystemMessage(content=system_prompt))
        all_messages.extend(messages)

        # Use structured output
        structured_client = self.client.with_structured_output(schema)

        try:
            response = await structured_client.ainvoke(all_messages)
            return response

        except Exception as e:
            logger.error(f"Structured generation error: {e}")
            raise

    async def generate_with_web_search(
        self,
        messages: list[BaseMessage],
        system_prompt: str | None = None,
        web_search_config: WebSearchConfig | None = None,
        previous_response_id: str | None = None,
    ) -> WebSearchResponse:
        """
        Generate a response using OpenAI Responses API with web search.

        This method bypasses LangChain and uses the OpenAI SDK directly
        to access the Responses API with built-in web search tool.

        Args:
            messages: Conversation history
            system_prompt: Optional system prompt to prepend
            web_search_config: Configuration for web search behavior
            previous_response_id: Optional response ID for conversation continuity

        Returns:
            WebSearchResponse with content, citations, and metrics
        """
        if self.provider != "openai":
            raise ValueError(
                f"Web search requires OpenAI provider. Current provider: {self.provider}"
            )

        from openai import AsyncOpenAI

        config = web_search_config or WebSearchConfig()

        # Create async OpenAI client
        client = AsyncOpenAI(api_key=self.settings.openai_api_key)

        # Convert LangChain messages to Responses API format
        input_items = []

        # Add system prompt as instructions if provided
        instructions = system_prompt

        for msg in messages:
            if isinstance(msg, HumanMessage):
                input_items.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                input_items.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                # Combine system messages into instructions
                if instructions:
                    instructions = f"{instructions}\n\n{msg.content}"
                else:
                    instructions = msg.content

        # Build web search tool configuration
        web_search_tool: dict = {"type": "web_search"}

        if config.allowed_domains:
            web_search_tool["search_context_size"] = "medium"
            # Note: allowed_domains goes in the tool config if supported

        if config.user_location:
            user_loc = {"type": "approximate"}
            if config.user_location.get("country"):
                user_loc["country"] = config.user_location["country"]
            if config.user_location.get("city"):
                user_loc["city"] = config.user_location["city"]
            if config.user_location.get("region"):
                user_loc["region"] = config.user_location["region"]
            web_search_tool["user_location"] = user_loc

        logger.debug(f"Web search config: {web_search_tool}")

        try:
            start_time = time.perf_counter()

            # Build request kwargs
            request_kwargs = {
                "model": self.model,
                "tools": [web_search_tool],
                "input": input_items,
            }

            if instructions:
                request_kwargs["instructions"] = instructions

            if previous_response_id:
                request_kwargs["previous_response_id"] = previous_response_id

            response = await client.responses.create(**request_kwargs)

            response_time = time.perf_counter() - start_time

            # Extract content and citations from response
            content = ""
            citations: list[Citation] = []
            sources: list[str] = []

            # Handle None or empty output
            if response.output:
                for item in response.output:
                    if item.type == "message":
                        # Handle None content
                        if item.content:
                            for content_item in item.content:
                                if content_item.type == "output_text":
                                    content = content_item.text or ""
                                    # Extract citations from annotations
                                    if (
                                        hasattr(content_item, "annotations")
                                        and content_item.annotations
                                    ):
                                        for ann in content_item.annotations:
                                            if ann.type == "url_citation":
                                                citations.append(
                                                    Citation(
                                                        url=ann.url,
                                                        title=ann.title or "",
                                                        start_index=ann.start_index,
                                                        end_index=ann.end_index,
                                                    )
                                                )
                    elif item.type == "web_search_call":
                        # Extract sources from web search action if available
                        if hasattr(item, "action") and hasattr(item.action, "sources"):
                            if item.action.sources:
                                sources.extend(item.action.sources)

            # Extract token usage
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, "usage") and response.usage:
                prompt_tokens = getattr(response.usage, "input_tokens", 0)
                completion_tokens = getattr(response.usage, "output_tokens", 0)

            logger.info(
                f"Web search response: citations={len(citations)}, "
                f"sources={len(sources)}, time={response_time:.2f}s"
            )

            return WebSearchResponse(
                content=content,
                citations=citations,
                sources=sources,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                response_time=response_time,
                response_id=response.id,
            )

        except Exception as e:
            logger.error(f"Web search generation error: {e}")
            raise


class MockLLMClient:
    """Mock LLM client for testing."""

    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """Return a mock response with usage metadata."""
        from langchain_core.messages import AIMessage

        response = AIMessage(content="This is a mock response for testing.")
        response.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 8,
        }
        return response


@lru_cache
def get_llm_service() -> LLMService:
    """Get cached LLM service instance."""
    return LLMService(get_settings())
