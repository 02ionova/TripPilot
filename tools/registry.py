"""Native function schemas and safe typed dispatch for the five tools."""

import json

from pydantic import ValidationError

from schemas import (
    ActivityArgs,
    BuildArgs,
    FlightArgs,
    HotelArgs,
    ToolError,
    ToolResult,
    WeatherArgs,
)
from tools.activities import search_activities
from tools.common import ToolFailure
from tools.flights import search_flights
from tools.hotels import search_hotels
from tools.itinerary import build_itinerary
from tools.weather import get_weather

REGISTRY = {
    "get_weather": (WeatherArgs, get_weather, "Get simulated seasonal weather for all trip dates."),
    "search_flights": (
        FlightArgs,
        search_flights,
        "Search simulated Prague round trips; max_price is the group total.",
    ),
    "search_hotels": (
        HotelArgs,
        search_hotels,
        "Search simulated accommodation. Nightly limit covers all beds/rooms. Retry no_results with broader filters or hostels.",
    ),
    "search_activities": (
        ActivityArgs,
        search_activities,
        "Search simulated attractions and meals, matching dietary restrictions. Meals remain included regardless of interests/environment.",
    ),
    "build_itinerary": (
        BuildArgs,
        build_itinerary,
        "Validate a proposed daily schedule using trusted option IDs. Prices are resolved in Python. Requires every day, meals, minute times, airport buffers, 15-minute transfers, weather and pace compliance. Returns actionable errors.",
    ),
}


def tool_definitions():
    # Pydantic JSON schemas document arguments; dispatch validates even malformed calls.
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": model.model_json_schema(),
            },
        }
        for name, (model, _, description) in REGISTRY.items()
    ]


def execute_tool(name: str, arguments: str | dict) -> dict:
    try:
        if name not in REGISTRY:
            raise ToolFailure("unknown_tool", f"Unknown tool: {name}", list(REGISTRY))
        model, function, _ = REGISTRY[name]
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = function(model.model_validate(args))
        return result.model_dump(mode="json")
    except ToolFailure as exc:
        return ToolResult(status="error", error=exc.error).model_dump(mode="json")
    except (ValidationError, ValueError, TypeError) as exc:
        # Validation messages omit input values so accidental credentials are not echoed.
        detail = (
            "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                for e in exc.errors(include_input=False)
            )
            if isinstance(exc, ValidationError)
            else "Arguments must be valid JSON matching the tool schema."
        )
        return ToolResult(
            status="error",
            error=ToolError(
                code="invalid_arguments",
                message=detail,
                suggestions=["Review the JSON schema and correct the arguments."],
            ),
        ).model_dump(mode="json")
    except Exception:
        return ToolResult(
            status="error",
            error=ToolError(
                code="internal_tool_error",
                message="The tool could not complete.",
                suggestions=["Retry once with valid arguments; otherwise return error."],
            ),
        ).model_dump(mode="json")
