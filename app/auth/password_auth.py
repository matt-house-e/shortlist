"""Simple password authentication for development/testing."""

import chainlit as cl

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def password_auth_callback(username: str, password: str) -> cl.User | None:
    """
    Authenticate user with username and password.

    This is a simple authentication method suitable for development
    and testing. For production, use OAuth/SSO authentication.

    Args:
        username: User's username
        password: User's password

    Returns:
        Authenticated User object or None if authentication fails
    """
    settings = get_settings()

    # Check password
    if password != settings.auth_password:
        logger.warning(f"Failed login attempt for user: {username}")
        return None

    logger.info(f"User authenticated: {username}")

    return cl.User(
        identifier=username,
        metadata={
            "auth_method": "password",
            "role": "user",
        },
    )
