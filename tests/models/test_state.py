"""State schema tests."""

from app.models.state import create_initial_state


def test_create_initial_state():
    """Test initial state creation."""
    state = create_initial_state(
        user_id="test-user",
        session_id="test-session",
    )

    assert state["user_id"] == "test-user"
    assert state["session_id"] == "test-session"
    assert state["current_phase"] == "intake"


def test_create_initial_state_has_web_search_fields():
    """Test initial state includes web search fields."""
    state = create_initial_state(
        user_id="test-user",
        session_id="test-session",
    )

    assert state["web_search_citations"] == []
    assert state["web_search_sources"] == []
    assert state["openai_response_id"] is None


def test_create_initial_state_has_hitl_fields():
    """Test initial state includes HITL confirmation fields."""
    state = create_initial_state(
        user_id="test-user",
        session_id="test-session",
    )

    # HITL confirmation flags should all be False
    assert state["awaiting_requirements_confirmation"] is False
    assert state["awaiting_fields_confirmation"] is False
    assert state["awaiting_intent_confirmation"] is False

    # HITL pending data should be None
    assert state["action_choices"] is None
    assert state["pending_requirements_summary"] is None
    assert state["pending_field_definitions"] is None
    assert state["pending_intent"] is None
    assert state["pending_intent_details"] is None


def test_create_initial_state_has_living_table_fields():
    """Test initial state includes living table and requested_fields."""
    state = create_initial_state(
        user_id="test-user",
        session_id="test-session",
    )

    # Living table should be None initially
    assert state["living_table"] is None

    # Requested fields should be empty list
    assert state["requested_fields"] == []
