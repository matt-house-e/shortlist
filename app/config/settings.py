"""Application settings using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # LLM Configuration
    # -------------------------------------------------------------------------
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: Literal["openai", "anthropic", "mock"] = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7

    # -------------------------------------------------------------------------
    # Database Configuration
    # -------------------------------------------------------------------------
    # Named APP_DATABASE_URL to avoid Chainlit auto-detection of DATABASE_URL
    app_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent_template"

    # -------------------------------------------------------------------------
    # S3 Storage Configuration
    # -------------------------------------------------------------------------
    s3_bucket: str = "uploads"
    s3_endpoint_url: str | None = None  # None for real AWS, URL for LocalStack
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"

    # -------------------------------------------------------------------------
    # Authentication Configuration
    # -------------------------------------------------------------------------
    auth_method: Literal["password", "oauth"] = "password"
    auth_password: str = "changeme"

    # OAuth settings (when auth_method == "oauth")
    oauth_provider: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_tenant_id: str | None = None  # Azure AD

    # -------------------------------------------------------------------------
    # Chainlit Configuration
    # -------------------------------------------------------------------------
    chainlit_auth_secret: str = ""
    chainlit_host: str = "0.0.0.0"
    chainlit_port: int = 8000
    enable_data_layer: bool = False  # Set True when running with PostgreSQL

    # -------------------------------------------------------------------------
    # Web Search Configuration (OpenAI Responses API)
    # -------------------------------------------------------------------------
    web_search_enabled: bool = False
    web_search_allowed_domains: list[str] = []
    web_search_user_country: str | None = None
    web_search_user_city: str | None = None
    web_search_user_region: str | None = None

    # -------------------------------------------------------------------------
    # Lattice Enrichment Configuration
    # -------------------------------------------------------------------------
    tavily_api_key: str = ""
    lattice_model: str = "gpt-4.1-mini"
    lattice_temperature: float = 0.2
    lattice_max_tokens: int = 8000
    lattice_batch_size: int = 20
    lattice_max_workers: int = 30
    lattice_row_delay: float = 0.1
    lattice_enable_checkpointing: bool = True
    lattice_checkpoint_interval: int = 100
    lattice_max_retries: int = 3

    # -------------------------------------------------------------------------
    # Logging Configuration
    # -------------------------------------------------------------------------
    log_level: str = "INFO"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
