"""Shared dataset loading and recoverable tool errors."""

import json
from datetime import timedelta

from config import ROOT
from schemas import ToolError, ToolResult


class ToolFailure(ValueError):
    def __init__(self, code: str, message: str, suggestions: list[str]):
        super().__init__(message)
        self.error = ToolError(code=code, message=message, suggestions=suggestions)


def load(kind: str, destination: str) -> list | dict:
    data = json.loads((ROOT / "data" / f"{kind}.json").read_text())["destinations"]
    city = destination.strip().title()
    if city not in data:
        raise ToolFailure("unsupported_destination", f"{destination} is not supported.", list(data))
    return data[city]


def dates(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def no_results(message: str):
    raise ToolFailure(
        "no_results",
        message,
        [
            "Increase the price limit.",
            "Remove type or environment filters.",
            "Try hostel accommodation or free activities.",
        ],
    )


def success(data):
    return ToolResult(status="ok", data=data)
