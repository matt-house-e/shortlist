"""Retry utilities for external service calls."""

import logging

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# For OpenAI API calls - retry on transient + rate limit errors
openai_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),  # longer max for 429
    retry=retry_if_exception_type(
        (
            ConnectionError,
            TimeoutError,
            RateLimitError,  # 429 - retry with backoff
            APIConnectionError,  # Network issues
            APITimeoutError,  # Request timeout
        )
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# For web search - more lenient, fail fast
web_search_retry = retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=1, max=5),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
