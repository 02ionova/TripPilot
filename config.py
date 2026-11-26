"""Environment settings; dotenv never replaces existing environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    max_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_AGENT_ITERATIONS", "15"))
    )
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
    serpapi_api_key: str = field(
        default_factory=lambda: os.getenv("SERPAPI_API_KEY", ""), repr=False
    )
    data_mode: str = field(default_factory=lambda: os.getenv("DATA_MODE", "live").lower())
    max_serpapi_requests: int = field(
        default_factory=lambda: int(os.getenv("MAX_SERPAPI_REQUESTS_PER_RUN", "15"))
    )
    enable_ai_fallback: bool = field(
        default_factory=lambda: (
            os.getenv("ENABLE_AI_FALLBACK", "true").lower() in {"true", "1", "yes"}
        )
    )
    timeout: float = 60.0
    http_timeout: float = 25.0
    estimated_meal_eur: float = 15.0
    estimated_activity_eur: float = 15.0
    estimated_transport_per_day: float = 8.0
    estimated_airport_transfer_per_leg: float = 12.0

    def __post_init__(self):
        if self.data_mode not in {"live", "demo"}:
            raise ValueError("DATA_MODE must be live or demo.")
        if not 1 <= self.max_serpapi_requests <= 50:
            raise ValueError("MAX_SERPAPI_REQUESTS_PER_RUN must be between 1 and 50.")
        if not 1 <= self.max_iterations <= 50:
            raise ValueError("MAX_AGENT_ITERATIONS must be between 1 and 50.")
