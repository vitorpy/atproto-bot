"""Configuration management for the ATproto bot."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr


class BlueskyConfig(BaseModel):
    """Bluesky/ATproto connection settings."""

    handle: str = Field(..., description="Bot's Bluesky handle")
    app_password: SecretStr = Field(..., description="App password for authentication")
    owner_did: str = Field(..., pattern=r"^did:plc:[a-z0-9]+$", description="Owner's DID")


class LLMConfig(BaseModel):
    """LLM provider settings."""

    provider: Literal["anthropic", "openai"] = "anthropic"
    api_key: SecretStr = Field(..., description="API key for LLM provider")
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class BotConfig(BaseModel):
    """Bot behavior settings."""

    poll_interval: int = Field(default=30, ge=5, description="Seconds between notification checks")
    max_thread_depth: int = Field(default=50, ge=1, le=100)
    rate_limit_per_hour: int = Field(default=20, ge=1)
    max_post_length: int = Field(default=300, ge=1, le=300)

    # Database settings
    database_path: str = Field(
        default="~/.atproto-bot/bot.db", description="Path to SQLite database file"
    )
    cleanup_old_data_days: int = Field(default=30, description="Clean up data older than N days")


class Config(BaseModel):
    """Root configuration model."""

    bluesky: BlueskyConfig
    llm: LLMConfig
    bot: BotConfig = BotConfig()


def load_config(config_path: str | Path = "config.yaml") -> Config:
    """Load and validate configuration from YAML file.

    Supports ${VAR_NAME} syntax for environment variable expansion.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Validated Config object.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValidationError: If config is invalid.
        ValueError: If referenced environment variable is not set.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config.example.yaml to config.yaml and fill in your values."
        )

    with path.open() as f:
        raw_config = yaml.safe_load(f)

    # Expand environment variables in the format ${VAR_NAME}
    def expand_env_vars(obj):
        if isinstance(obj, dict):
            return {k: expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            value = os.getenv(env_var)
            if value is None:
                raise ValueError(f"Environment variable '{env_var}' is not set")
            return value
        return obj

    raw_config = expand_env_vars(raw_config)

    return Config(**raw_config)
