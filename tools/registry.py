"""Native function schemas and safe typed dispatch for Live and Demo tools."""

import json

from pydantic import ValidationError

from schemas import (
    ActivityArgs,
    BuildArgs,
    FlightArgs,
    HotelArgs,
    LiveBuildArgs,
    RestaurantArgs,
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
        "Search simulated round trips between the entered cities; max_price is the group total.",
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


LIVE_REGISTRY = {
    "get_weather": (
        WeatherArgs,
        "Retrieve Open-Meteo forecast up to 16 days ahead or explicitly labeled historical climate estimates for later dates.",
    ),
    "search_flights": (
        FlightArgs,
        "Retrieve complete EUR round trips via Google Flights with both outbound and return schedules. Return-selection needs an extra request; outbound_index explores another outbound. max_price is the whole party total; reuse cached searches.",
    ),
    "search_hotels": (
        HotelArgs,
        "Retrieve Google Hotels prices for the destination arrival/check-out dates. max_nightly_price is the combined nightly amount. Multiple rooms and totals derived from nightly rates are explicitly marked estimates; taxes may be unknown. page_token optionally retrieves another page and spends a request.",
    ),
    "search_activities": (
        ActivityArgs,
        "Find real Google Maps attractions. Missing admission prices use explicit EUR 15/person estimates, never zero. Includes coordinates, operating hours when available, source links and ratings. query optionally refines a bulk search.",
    ),
    "search_restaurants": (
        RestaurantArgs,
        "Find real Google Maps restaurants/cafes using a bulk dietary/location query. Meal costs are explicitly estimated from price tiers or EUR 15/person. Dietary indications are not certification; check notes. near optionally clusters venues near coordinates.",
    ),
    "build_itinerary": (
        LiveBuildArgs,
        "Use auto_schedule=true (default) to arrange chosen attraction IDs and fill required meals using only retrieved venues; proposed slot times are not binding. Validate selected IDs exclusively from this run's retrieved results. Requires all trip days, original request, flight-compatible hotel dates, meals, opening hours and geographic transfer gaps. Returns precise feedback and a programmatically verified budget. Does not make API requests; never invent IDs or amounts.",
    ),
}


def tool_definitions(mode="demo", runtime=None):
    if mode == "live":
        definitions = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, (model, description) in LIVE_REGISTRY.items()
        ]
        if runtime:
            builder = next(
                t["function"]["parameters"]
                for t in definitions
                if t["function"]["name"] == "build_itinerary"
            )
            # Ground ID choices in the current run rather than asking the model to
            # repeatedly copy opaque provider IDs from a long conversation.
            if runtime.flights:
                builder["properties"]["flight_id"]["enum"] = list(runtime.flights)
            if runtime.hotels:
                for variant in builder["properties"]["hotel_id"].get("anyOf", []):
                    if variant.get("type") == "string":
                        variant["enum"] = list(runtime.hotels)
            if runtime.activities:
                builder["$defs"]["ScheduledSelection"]["properties"]["activity_id"]["enum"] = list(
                    runtime.activities
                )
            builder["properties"]["request"]["const"] = runtime.request.model_dump(mode="json")
        return definitions

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


def execute_tool(
    name: str, arguments: str | dict, runtime=None, *, mode: str | None = None
) -> dict:
    from config import Settings

    live = runtime is not None or (mode or Settings().data_mode) == "live"
    try:
        if live:
            if name not in LIVE_REGISTRY:
                raise ToolFailure("unknown_tool", f"Unknown tool: {name}", list(LIVE_REGISTRY))
            if runtime is None:
                raise ToolFailure(
                    "missing_live_context",
                    "Live tools require a per-run result store.",
                    ["Run through TravelAgent or pass an explicit LiveTools context."],
                )
            model, _ = LIVE_REGISTRY[name]
            raw = json.loads(arguments) if isinstance(arguments, str) else arguments
            return getattr(runtime, name)(model.model_validate(raw)).model_dump(mode="json")
        if name not in REGISTRY:
            raise ToolFailure("unknown_tool", f"Unknown tool: {name}", list(REGISTRY))
        model, function, _ = REGISTRY[name]
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        result = function(model.model_validate(args))
        return result.model_dump(mode="json")
    except ToolFailure as exc:
        return ToolResult(
            status="error", error=exc.error, data_source="live" if live else "simulated"
        ).model_dump(mode="json")
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
            data_source="live" if live else "simulated",
            error=ToolError(
                code="invalid_arguments",
                message=detail,
                suggestions=["Review the JSON schema and correct the arguments."],
            ),
        ).model_dump(mode="json")
    except Exception:
        return ToolResult(
            status="error",
            data_source="live" if live else "simulated",
            error=ToolError(
                code="internal_tool_error",
                message="The tool could not complete.",
                suggestions=["Retry once with valid arguments; otherwise return error."],
            ),
        ).model_dump(mode="json")
