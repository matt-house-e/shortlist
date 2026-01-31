"""OAuth/SSO authentication provider (Placeholder)."""

import chainlit as cl

from app.utils.logger import get_logger

logger = get_logger(__name__)


async def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
) -> cl.User | None:
    """
    Handle OAuth authentication callback.

    This is called after the user completes OAuth authentication
    with the configured provider (Azure AD, Google, etc.).

    Args:
        provider_id: OAuth provider identifier
        token: OAuth access token
        raw_user_data: User data from the OAuth provider
        default_user: Default user object from Chainlit

    Returns:
        Authenticated User object or None if authentication fails
    """
    logger.info(f"OAuth callback from provider: {provider_id}")

    # TODO: Implement OAuth authentication
    #
    # Example for Azure AD:
    # if provider_id == "azure":
    #     email = raw_user_data.get("email") or raw_user_data.get("preferred_username")
    #     name = raw_user_data.get("name", email)
    #
    #     # Optionally fetch additional user data from Microsoft Graph API
    #     # user_details = await fetch_graph_api_user(token)
    #
    #     return cl.User(
    #         identifier=email,
    #         metadata={
    #             "auth_method": "oauth",
    #             "provider": provider_id,
    #             "name": name,
    #             "email": email,
    #             "roles": raw_user_data.get("roles", []),
    #         },
    #     )

    # Fallback to default user
    logger.warning(f"OAuth provider not implemented: {provider_id}")
    return default_user


# =============================================================================
# Provider-Specific Helpers
# =============================================================================


async def fetch_azure_user_details(access_token: str) -> dict:
    """
    Fetch user details from Microsoft Graph API.

    Args:
        access_token: OAuth access token

    Returns:
        User details from Graph API
    """
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()
