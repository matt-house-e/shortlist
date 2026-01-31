"""Test the router pattern and ADVISE flow."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.workflow import create_workflow, router_node
from app.models.state import AgentState
from app.services.llm import get_llm_service


@pytest.fixture
def llm_service():
    """Get LLM service for tests."""
    return get_llm_service()


class TestRouterNode:
    """Tests for the router node."""

    @pytest.mark.asyncio
    async def test_router_routes_to_intake_by_default(self):
        """Router should route to INTAKE when phase is intake or unset."""
        state = AgentState(messages=[], current_phase="intake")
        result = await router_node(state)
        assert result.goto == "intake"

    @pytest.mark.asyncio
    async def test_router_routes_to_intake_when_unset(self):
        """Router should route to INTAKE when current_phase is not set."""
        state = AgentState(messages=[])
        result = await router_node(state)
        assert result.goto == "intake"

    @pytest.mark.asyncio
    async def test_router_routes_to_advise(self):
        """Router should route to ADVISE when phase is advise."""
        state = AgentState(messages=[], current_phase="advise")
        result = await router_node(state)
        assert result.goto == "advise"

    @pytest.mark.asyncio
    async def test_router_routes_research_to_advise(self):
        """Router should route to ADVISE when phase is research (edge case)."""
        state = AgentState(messages=[], current_phase="research")
        result = await router_node(state)
        assert result.goto == "advise"


class TestWorkflowIntegration:
    """Integration tests for the workflow with router pattern."""

    @pytest.mark.asyncio
    async def test_workflow_has_router_node(self, llm_service):
        """Workflow should have a router node."""
        workflow = create_workflow(llm_service)
        # The compiled graph should have router as a node
        assert workflow is not None

    @pytest.mark.asyncio
    async def test_first_message_reaches_intake(self, llm_service):
        """First message should be routed through intake."""
        workflow = create_workflow(llm_service)

        # Simulate first message
        input_state = {
            "messages": [HumanMessage(content="I want to buy a laptop")],
            "current_phase": "intake",
        }
        config = {"configurable": {"thread_id": "test-session-1"}}

        result = await workflow.ainvoke(input_state, config)

        # Should have processed through intake
        assert result.get("current_node") == "intake"
        assert len(result.get("messages", [])) > 1  # At least input + response

    @pytest.mark.asyncio
    async def test_advise_phase_message_reaches_advise(self, llm_service):
        """Message during advise phase should go to advise, not intake."""
        workflow = create_workflow(llm_service)
        config = {"configurable": {"thread_id": "test-session-2"}}

        # Set up state as if we're in ADVISE phase with results already presented
        input_state = {
            "messages": [
                HumanMessage(content="I want a laptop"),
                AIMessage(content="Here are your options..."),
                HumanMessage(content="Tell me more about the MacBook"),
            ],
            "current_phase": "advise",
            "advise_has_presented": True,
            "user_requirements": {"product_type": "laptop"},
            "comparison_table": {
                "fields": [{"name": "price", "data_type": "string"}],
                "candidates": [{"name": "MacBook Air M3", "price": "£999"}],
            },
        }

        result = await workflow.ainvoke(input_state, config)

        # Should stay in advise phase (question intent)
        assert result.get("current_phase") in ["advise", "complete"]
        # Should NOT have looped back through intake -> research
        # (if it had, current_node would be research)
        assert result.get("current_node") != "research"


class TestLoopPrevention:
    """Tests to verify the infinite loop bug is fixed."""

    @pytest.mark.asyncio
    async def test_full_flow_no_loop(self, llm_service):
        """
        Simulate the exact scenario from the bug report:
        1. User: "I want to buy a laptop"
        2. System stays in INTAKE (asks for more)
        3. User: "Apple, M chip, under £2000"
        4. INTAKE -> RESEARCH -> ADVISE
        5. ADVISE should present and STOP (not loop)
        """
        workflow = create_workflow(llm_service)
        config = {"configurable": {"thread_id": "test-loop-prevention"}}

        # Message 1: Initial request
        result1 = await workflow.ainvoke(
            {
                "messages": [HumanMessage(content="I want to buy a laptop")],
                "current_phase": "intake",
            },
            config,
        )

        # Should stay in INTAKE asking for more details
        assert result1.get("current_phase") == "intake"
        assert result1.get("current_node") == "intake"

        # Message 2: Provide requirements
        result2 = await workflow.ainvoke(
            {
                "messages": [
                    HumanMessage(content="It should be from Apple, have an M chip, under £2000")
                ],
            },
            config,
        )

        # Should now be in ADVISE phase (after INTAKE -> RESEARCH -> ADVISE)
        assert result2.get("current_phase") == "advise"

        # Key check: advise_has_presented should be True
        # This means ADVISE presented results and returned __end__
        # NOT that it looped back through INTAKE
        assert result2.get("advise_has_presented") is True

        # Should have candidates from research
        assert result2.get("candidates") is not None
        assert len(result2.get("candidates", [])) > 0

        # Message count check: should be reasonable (not inflated from looping)
        # Expected: User1 + AI1 (intake) + User2 + AI2 (research msg) + AI3 (advise presentation)
        messages = result2.get("messages", [])
        assert len(messages) <= 10, f"Too many messages ({len(messages)}), suggests looping"

    @pytest.mark.asyncio
    async def test_advise_presents_then_waits(self, llm_service):
        """
        Verify ADVISE mode switching:
        - First entry: presents results, sets advise_has_presented=True
        - Does NOT analyze intent on first entry
        """
        workflow = create_workflow(llm_service)
        config = {"configurable": {"thread_id": "test-advise-modes"}}

        # Set up state as if RESEARCH just completed
        input_state = {
            "messages": [
                HumanMessage(content="I want a laptop from Apple"),
                AIMessage(content="Got it, searching..."),
            ],
            "current_phase": "advise",
            "advise_has_presented": False,  # First entry to ADVISE
            "user_requirements": {"product_type": "laptop", "must_haves": ["Apple"]},
            "comparison_table": {
                "fields": [{"name": "price", "data_type": "string"}],
                "candidates": [
                    {"name": "MacBook Air M3", "price": "£999"},
                    {"name": "MacBook Pro 14", "price": "£1999"},
                ],
            },
        }

        result = await workflow.ainvoke(input_state, config)

        # After first entry, should have presented and set flag
        assert result.get("advise_has_presented") is True
        # Should still be in advise phase (waiting for user)
        assert result.get("current_phase") == "advise"
        # Should NOT have routed anywhere (stayed at advise, returned __end__)
        assert result.get("current_node") == "advise"
