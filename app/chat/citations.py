"""Citation formatting utilities for chat responses."""


def format_response_with_citations(content: str, citations: list[dict]) -> str:
    """
    Append a Sources section to the response with clickable citation links.

    Args:
        content: The response text
        citations: List of citation dicts with url, title, start_index, end_index

    Returns:
        Response with appended sources section
    """
    if not citations:
        return content

    # Deduplicate citations by URL
    seen_urls = set()
    unique_citations = []
    for cite in citations:
        if cite["url"] not in seen_urls:
            seen_urls.add(cite["url"])
            unique_citations.append(cite)

    # Build sources section
    sources = "\n\n---\n**Sources:**\n"
    for cite in unique_citations:
        title = cite.get("title", cite["url"])
        sources += f"- [{title}]({cite['url']})\n"

    return content + sources
