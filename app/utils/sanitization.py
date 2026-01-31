"""Input sanitization and validation utilities."""

import re
import unicodedata
from html import escape


def sanitize_input(
    text: str,
    max_length: int = 5000,
    strip_html: bool = True,
    strip_control_chars: bool = True,
    normalize_unicode: bool = True,
) -> str:
    """
    Sanitize user input for safe processing.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length (truncates if exceeded)
        strip_html: Whether to escape HTML entities
        strip_control_chars: Whether to remove control characters
        normalize_unicode: Whether to apply NFKC normalization

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Apply NFKC normalization to handle homoglyphs and compatibility characters
    if normalize_unicode:
        text = unicodedata.normalize("NFKC", text)

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]

    # Strip control characters (except newlines and tabs)
    if strip_control_chars:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Escape HTML entities
    if strip_html:
        text = escape(text)

    # Normalize whitespace (collapse multiple spaces, preserve newlines)
    text = re.sub(r"[^\S\n]+", " ", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def validate_file_extension(filename: str, allowed_extensions: set[str]) -> bool:
    """
    Validate file extension against allowed list.

    Args:
        filename: File name to validate
        allowed_extensions: Set of allowed extensions (lowercase, with dot)

    Returns:
        True if extension is allowed
    """
    if not filename:
        return False

    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in allowed_extensions


def validate_content_length(content: str | bytes, max_bytes: int) -> bool:
    """
    Validate content size doesn't exceed limit.

    Args:
        content: Content to validate
        max_bytes: Maximum allowed size in bytes

    Returns:
        True if content is within limit
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return len(content) <= max_bytes
