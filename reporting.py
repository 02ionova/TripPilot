"""Build one sanitized report archive without provider or model requests."""

import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

from information import information_groups
from schemas import FinalResponse
from tracing import redact


def report_markdown(result: FinalResponse, trace: dict) -> str:
    """Human-readable itinerary plus structured files for technical review."""
    lines = ["# TripPilot AI — Travel report", "", f"Status: {result.status}", "", result.message]
    plan = result.itinerary
    if plan:
        s = plan.trip_summary
        lines += [
            "",
            f"## {s.origin} → {s.destination}",
            f"{s.start_date} – {s.end_date}; {s.travelers} traveler(s); EUR",
            "",
            "## Budget",
        ]
        lines += [
            f"- {key.replace('_', ' ').title()}: EUR {value:.2f}"
            for key, value in plan.budget_breakdown.model_dump().items()
        ]
        flight = plan.selected_flights
        lines += [
            "",
            "## Selected round-trip flight",
            f"{flight.airline}: EUR {flight.total_price:.2f} for all travelers",
        ]
        for title, legs in [
            ("Outbound", flight.outbound_segments),
            ("Return", flight.return_segments),
        ]:
            lines += [f"### {title}"]
            lines += [
                f"- {p.airline} {p.flight_number or ''}: {p.departure_airport} {p.departure} → {p.arrival_airport} {p.arrival} (airport local times)"
                for p in legs
            ]
        if flight.search_url:
            lines.append(f"Source: {flight.search_url}")
        hotel = plan.selected_accommodation
        if hotel:
            lines += [
                "",
                "## Accommodation",
                f"{hotel.name}; {hotel.nights} nights; {hotel.rooms} room(s); EUR {hotel.total_cost:.2f} total",
                hotel.address or hotel.neighborhood,
            ]
            if hotel.url:
                lines.append(f"Source: {hotel.url}")
        for day in plan.daily_itinerary:
            lines += [
                "",
                f"## {day.date} — {day.title}",
                f"{day.weather.information_type}: {day.weather.conditions}; {day.weather.min_temperature}–{day.weather.max_temperature} °C",
                f"Daily expenses: EUR {day.estimated_cost:.2f} (flights/accommodation charged separately)",
            ]
            lines += [
                f"- {slot.start_time:%H:%M}–{slot.end_time:%H:%M} | {slot.meal or 'Visit'} | {slot.activity.name} | EUR {slot.total_cost:.2f}"
                + (f" | {slot.activity.address}" if slot.activity.address else "")
                + (f" | {slot.activity.url}" if slot.activity.url else "")
                for slot in day.schedule
            ]
    lines += [
        "",
        "## Report files",
        "- result.json: complete structured response, itinerary, prices and provenance.",
        "- request.json: original trip request.",
        "- execution_trace.json: observable model/tool/provider events, errors and timings.",
        "- runtime.log: concise chronological action log.",
        "- information.json: notices and practical notes shown in the information control.",
        "- budget_validation.json: recorded budget validation (null when no validated plan exists).",
        "",
        f"Run ID: {trace.get('run_id', 'unavailable')}",
        "This archive does not contain API keys or hidden model reasoning.",
    ]
    return "\n".join(lines) + "\n"


def create_report_archive(result: FinalResponse, trace: dict, mode: str) -> bytes:
    """Package only current-run data; never read .env, caches or unrelated traces."""
    contents = {
        "result.json": result.model_dump(mode="json"),
        "request.json": trace.get("request"),
        "execution_trace.json": trace,
        "information.json": information_groups(mode, result),
        "budget_validation.json": trace.get("budget_validation"),
    }
    log = []
    for event in trace.get("events", []):
        detail = {
            key: event[key]
            for key in ("tool", "tool_call_id", "summary", "error", "duration_seconds", "counters")
            if key in event
        }
        if event.get("result"):
            detail["status"] = event["result"].get("status")
            if event["result"].get("error"):
                detail["error"] = event["result"]["error"]
        log.append(
            f"{event.get('timestamp', '')} [{event.get('kind', 'event')}] {json.dumps(redact(detail), ensure_ascii=False)}"
        )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, value in contents.items():
            archive.writestr(name, json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n")
        archive.writestr("README.md", redact(report_markdown(result, trace)))
        archive.writestr("runtime.log", redact("\n".join(log) + "\n"))
    return buffer.getvalue()
