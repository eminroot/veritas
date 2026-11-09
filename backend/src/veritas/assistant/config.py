"""The assistant's settings, read from the environment or backend/.env like the rest.

They are separate from veritas.settings so the assistant can be switched on and off on its
own: without an API key it is off, and the API answers 503 assistant_unavailable.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("VERITAS_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    """Kept on the server only; the web app never sees it."""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str | None = None
    """Only for reasoning models (for example "minimal" with gpt-5-mini); other models refuse it."""
    openai_timeout_seconds: float = Field(default=15, gt=0, le=60)
    """Shorter than the web app's 20 second limit, so a slow answer still comes back as an error."""

    assistant_max_output_tokens: int = Field(default=600, ge=50, le=4000)
    assistant_per_minute: int = Field(default=6, ge=1, le=120)
    """Questions one visitor (one IP address) may ask in a minute."""
    assistant_per_day: int = Field(default=60, ge=1, le=5000)
    """Questions one visitor may ask in 24 hours."""
    assistant_daily_budget: int = Field(default=2000, ge=1, le=1_000_000)
    """Model calls in a day for all visitors together, per API process: a ceiling on the bill."""

    @property
    def enabled(self) -> bool:
        return self.openai_api_key is not None and bool(self.openai_api_key.get_secret_value())
