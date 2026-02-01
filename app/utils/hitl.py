"""HITL (Human-in-the-Loop) utilities shared across agent nodes."""


def parse_hitl_choice(content: str) -> str | None:
    """Extract choice from HITL synthetic message.

    Args:
        content: Message in format "[HITL:checkpoint:choice]"

    Returns:
        The choice string, or None if not a valid HITL message
    """
    if not content.startswith("[HITL:"):
        return None
    try:
        inner = content[6:-1]  # Strip "[HITL:" and "]"
        parts = inner.split(":", 1)
        if len(parts) == 2:
            return parts[1]
    except Exception:
        pass
    return None


def clear_hitl_flags() -> dict:
    """Return dict of cleared HITL state flags for state updates."""
    return {
        "awaiting_requirements_confirmation": False,
        "awaiting_fields_confirmation": False,
        "awaiting_intent_confirmation": False,
        "action_choices": None,
        "pending_requirements_summary": None,
        "pending_field_definitions": None,
        "pending_intent": None,
        "pending_intent_details": None,
    }


def is_hitl_message(content: str) -> bool:
    """Check if content is a HITL synthetic message."""
    return content.startswith("[HITL:") and content.endswith("]")
