"""Central configuration. All values come from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Snapshot of the environment. Use `get_settings()` so tests can reload."""

    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    neon_database_url: str = field(default_factory=lambda: os.getenv("NEON_DATABASE_URL", ""))
    langfuse_public_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY", ""))
    langfuse_secret_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY", ""))
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_pr_draft: bool = field(default_factory=lambda: _bool("GITHUB_PR_DRAFT", True))
    webhook_secret: str = field(default_factory=lambda: os.getenv("WEBHOOK_SECRET", ""))
    confidence_threshold: float = field(default_factory=lambda: float(os.getenv("CONFIDENCE_THRESHOLD", "0.85")))
    max_iterations: int = field(default_factory=lambda: int(os.getenv("MAX_ITERATIONS", "3")))
    context_radius: int = field(default_factory=lambda: int(os.getenv("CODE_CONTEXT_RADIUS", "50")))


settings = Settings()

AGENT_VERSION = "1.0.0-opspulse"
