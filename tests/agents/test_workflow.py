"""Workflow tests."""

import pytest


@pytest.mark.asyncio
async def test_workflow_creation(mock_settings):
    """Test workflow can be created."""
    from app.agents.workflow import create_workflow
    from app.services.llm import LLMService

    llm_service = LLMService(mock_settings)
    workflow = create_workflow(llm_service)

    assert workflow is not None
