"""LLM service tests."""


def test_llm_service_init(mock_settings):
    """Test LLM service initialization."""
    from app.services.llm import LLMService

    service = LLMService(mock_settings)
    assert service.provider == "mock"


def test_web_search_config_defaults():
    """Test WebSearchConfig default values."""
    from app.services.llm import WebSearchConfig

    config = WebSearchConfig()
    assert config.enabled is True
    assert config.allowed_domains is None
    assert config.user_location is None


def test_web_search_config_with_values():
    """Test WebSearchConfig with custom values."""
    from app.services.llm import WebSearchConfig

    config = WebSearchConfig(
        enabled=True,
        allowed_domains=["example.com", "docs.example.com"],
        user_location={"country": "US", "city": "San Francisco"},
    )
    assert config.enabled is True
    assert config.allowed_domains == ["example.com", "docs.example.com"]
    assert config.user_location == {"country": "US", "city": "San Francisco"}


def test_citation_dataclass():
    """Test Citation dataclass."""
    from app.services.llm import Citation

    citation = Citation(
        url="https://example.com",
        title="Example Page",
        start_index=100,
        end_index=150,
    )
    assert citation.url == "https://example.com"
    assert citation.title == "Example Page"
    assert citation.start_index == 100
    assert citation.end_index == 150


def test_web_search_response_defaults():
    """Test WebSearchResponse default values."""
    from app.services.llm import WebSearchResponse

    response = WebSearchResponse(content="Test response")
    assert response.content == "Test response"
    assert response.citations == []
    assert response.sources == []
    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0
    assert response.response_time == 0.0
    assert response.response_id is None


def test_web_search_requires_openai_provider(mock_settings):
    """Test that web search raises error for non-OpenAI providers."""
    import pytest

    from app.services.llm import LLMService, WebSearchConfig

    service = LLMService(mock_settings)

    async def test_generate():
        await service.generate_with_web_search(
            messages=[],
            web_search_config=WebSearchConfig(),
        )

    import asyncio

    with pytest.raises(ValueError, match="Web search requires OpenAI provider"):
        asyncio.get_event_loop().run_until_complete(test_generate())
