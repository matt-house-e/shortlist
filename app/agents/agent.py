"""Main agent node - Core conversation logic."""

from langchain_core.messages import AIMessage

from app.config import get_settings
from app.models.state import AgentState
from app.services.llm import WebSearchConfig, get_llm_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Default system prompt - customize for your use case
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant. Be concise, accurate, and helpful.
If you don't know something, say so rather than making things up."""


async def agent_node(state: AgentState) -> dict:
    """
    Main agent node that processes user requests.

    This is where the core agent logic lives. It:
    1. Retrieves conversation context from state
    2. Optionally searches knowledge bases or uses web search
    3. Generates a response using the LLM
    4. Returns updated state with the response and metrics

    Args:
        state: Current workflow state

    Returns:
        State updates including the assistant's response and metrics
    """
    logger.info("Agent node processing")

    # Get conversation history
    messages = state.get("messages", [])

    # Get current metrics
    current_turn = state.get("turn_number", 0)
    cumulative_prompt = state.get("cumulative_prompt_tokens", 0)
    cumulative_completion = state.get("cumulative_completion_tokens", 0)

    # Get previous response ID for conversation continuity
    previous_response_id = state.get("openai_response_id")

    try:
        llm_service = get_llm_service()
        settings = get_settings()

        # Check if web search is enabled and provider is OpenAI
        use_web_search = settings.web_search_enabled and settings.llm_provider == "openai"

        if settings.web_search_enabled and settings.llm_provider != "openai":
            logger.warning(
                "Web search requires OpenAI provider. "
                f"Current provider: {settings.llm_provider}. "
                "Falling back to standard generation."
            )

        if use_web_search:
            # Build user location config if provided
            user_location = None
            if settings.web_search_user_country:
                user_location = {
                    "country": settings.web_search_user_country,
                }
                if settings.web_search_user_city:
                    user_location["city"] = settings.web_search_user_city
                if settings.web_search_user_region:
                    user_location["region"] = settings.web_search_user_region

            # Use Responses API with web search
            web_search_config = WebSearchConfig(
                enabled=True,
                allowed_domains=settings.web_search_allowed_domains or None,
                user_location=user_location,
            )

            llm_response = await llm_service.generate_with_web_search(
                messages,
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                web_search_config=web_search_config,
                previous_response_id=previous_response_id,
            )

            # Update cumulative metrics
            new_turn = current_turn + 1
            new_prompt_tokens = cumulative_prompt + llm_response.prompt_tokens
            new_completion_tokens = cumulative_completion + llm_response.completion_tokens

            logger.info(
                f"Turn {new_turn} metrics (web search): "
                f"prompt={llm_response.prompt_tokens}, "
                f"completion={llm_response.completion_tokens}, "
                f"time={llm_response.response_time:.2f}s, "
                f"citations={len(llm_response.citations)}"
            )

            # Convert citations to dicts for state storage
            citation_dicts = [
                {
                    "url": c.url,
                    "title": c.title,
                    "start_index": c.start_index,
                    "end_index": c.end_index,
                }
                for c in llm_response.citations
            ]

            return {
                "messages": [AIMessage(content=llm_response.content)],
                "phase": "complete",
                "current_node": "agent",
                "turn_number": new_turn,
                "cumulative_prompt_tokens": new_prompt_tokens,
                "cumulative_completion_tokens": new_completion_tokens,
                "last_llm_response_time": llm_response.response_time,
                "web_search_citations": citation_dicts,
                "web_search_sources": llm_response.sources,
                "openai_response_id": llm_response.response_id,
            }

        else:
            # Standard LangChain path
            llm_response = await llm_service.generate(
                messages,
                system_prompt=DEFAULT_SYSTEM_PROMPT,
            )

            # Update cumulative metrics
            new_turn = current_turn + 1
            new_prompt_tokens = cumulative_prompt + llm_response.prompt_tokens
            new_completion_tokens = cumulative_completion + llm_response.completion_tokens

            logger.info(
                f"Turn {new_turn} metrics: "
                f"prompt={llm_response.prompt_tokens}, "
                f"completion={llm_response.completion_tokens}, "
                f"time={llm_response.response_time:.2f}s, "
                f"cumulative_prompt={new_prompt_tokens}, "
                f"cumulative_completion={new_completion_tokens}"
            )

            return {
                "messages": [AIMessage(content=llm_response.content)],
                "phase": "complete",
                "current_node": "agent",
                "turn_number": new_turn,
                "cumulative_prompt_tokens": new_prompt_tokens,
                "cumulative_completion_tokens": new_completion_tokens,
                "last_llm_response_time": llm_response.response_time,
            }

    except Exception as e:
        logger.error(f"Agent error: {e}")
        return {
            "messages": [AIMessage(content=f"I encountered an error: {str(e)}")],
            "phase": "error",
            "current_node": "agent",
        }
