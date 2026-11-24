"""Environment settings; dotenv never replaces existing environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    max_iterations: int = int(os.getenv("MAX_AGENT_ITERATIONS", "15"))
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
    timeout: float = 60.0

    def __post_init__(self):
        if not 1 <= self.max_iterations <= 50:
            raise ValueError("MAX_AGENT_ITERATIONS must be between 1 and 50.")
