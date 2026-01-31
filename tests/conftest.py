"""Pytest fixtures."""

import pytest


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    from app.config import Settings
    return Settings(
        llm_provider="mock",
        openai_api_key="test-key",
        chainlit_auth_secret="test-secret",
    )
