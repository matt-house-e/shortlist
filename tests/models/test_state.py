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
    assert state["phase"] == "start"


def test_create_initial_state_has_web_search_fields():
    """Test initial state includes web search fields."""
    state = create_initial_state(
        user_id="test-user",
        session_id="test-session",
    )

    assert state["web_search_citations"] == []
    assert state["web_search_sources"] == []
    assert state["openai_response_id"] is None
