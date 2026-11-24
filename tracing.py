"""Sanitized observable execution logs; no chain-of-thought or credentials."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from config import ROOT


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if any(
                word in k.lower()
                for word in ("api_key", "authorization", "password", "secret", "access_token")
            )
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(x) for x in value]
    if isinstance(value, str):
        for key in (os.getenv("OPENAI_API_KEY", ""), os.getenv("SERPAPI_API_KEY", "")):
            if key:
                value = value.replace(key, "[REDACTED]")
        value = re.sub(
            r"(?i)(api_key|access_token|authorization)=([^&\s]+)", r"\1=[REDACTED]", value
        )
        return re.sub(r'(?i)(sk-[A-Za-z0-9_-]+|bearer\s+[^\s"\']+)', "[REDACTED]", value)
    return value


class Trace:
    def __init__(self, request, model, directory: Path | None = None, execution_mode="real_llm"):
        self.directory = directory or ROOT / "traces"
        self.start = perf_counter()
        self.data = {
            "run_id": str(uuid4()),
            "start_timestamp": now(),
            "end_timestamp": None,
            "execution_mode": execution_mode,
            "request": redact(request),
            "model": model,
            "iterations": [],
            "events": [],
            "final_response": None,
            "final_status": None,
            "budget_validation": None,
        }
        self.path = (
            self.directory
            / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{self.data['run_id']}.json"
        )

    def event(self, kind, **values):
        event = redact({"timestamp": now(), "kind": kind, **values})
        self.data["events"].append(event)
        return event

    def finish(self, response):
        self.data.update(
            end_timestamp=now(),
            duration_seconds=round(perf_counter() - self.start, 4),
            final_response=response.model_dump(mode="json"),
            final_status=response.status,
        )
        if response.itinerary:
            budget = response.itinerary.budget_breakdown
            self.data["budget_validation"] = {
                "valid": True,
                "total": budget.total,
                "remaining_budget": budget.remaining_budget,
            }
        self.data = redact(self.data)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(redact(self.data), indent=2, ensure_ascii=False) + "\n")
        return response
