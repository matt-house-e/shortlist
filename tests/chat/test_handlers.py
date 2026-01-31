"""Chat handler tests."""

from app.chat.handlers import format_response_with_citations


def test_format_response_with_no_citations():
    """Test formatting response with no citations."""
    content = "This is a response."
    result = format_response_with_citations(content, [])
    assert result == content


def test_format_response_with_citations():
    """Test formatting response with citations."""
    content = "This is a response with information."
    citations = [
        {
            "url": "https://example.com/page1",
            "title": "Example Page 1",
            "start_index": 0,
            "end_index": 10,
        },
        {
            "url": "https://example.com/page2",
            "title": "Example Page 2",
            "start_index": 15,
            "end_index": 25,
        },
    ]

    result = format_response_with_citations(content, citations)

    assert "---" in result
    assert "**Sources:**" in result
    assert "[Example Page 1](https://example.com/page1)" in result
    assert "[Example Page 2](https://example.com/page2)" in result


def test_format_response_deduplicates_citations():
    """Test that duplicate URLs are deduplicated."""
    content = "This is a response."
    citations = [
        {
            "url": "https://example.com/page1",
            "title": "Example Page 1",
            "start_index": 0,
            "end_index": 10,
        },
        {
            "url": "https://example.com/page1",  # Duplicate URL
            "title": "Example Page 1 Again",
            "start_index": 15,
            "end_index": 25,
        },
    ]

    result = format_response_with_citations(content, citations)

    # Should only appear once
    assert result.count("https://example.com/page1") == 1


def test_format_response_uses_url_as_fallback_title():
    """Test that URL is used as title fallback."""
    content = "This is a response."
    citations = [
        {
            "url": "https://example.com/page1",
            "start_index": 0,
            "end_index": 10,
        },
    ]

    result = format_response_with_citations(content, citations)
    assert "[https://example.com/page1](https://example.com/page1)" in result
