"""CLI independent of Streamlit: python main.py --input examples/rome.json."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from agent import TravelAgent
from config import ROOT, Settings
from display import display_date


def main() -> int:
    parser = argparse.ArgumentParser(description="TripPilot AI — live travel planning")
    parser.add_argument("--mode", choices=["live", "demo"], default=None)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--demonstrate-recovery",
        action="store_true",
        help="Enable a deliberately restrictive initial hotel search for the course recovery demonstration.",
    )
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text())
    except (OSError, json.JSONDecodeError):
        print("Cannot read input: provide an existing, valid JSON file.")
        return 2
    settings = Settings()
    if args.mode:
        settings = replace(settings, data_mode=args.mode)
    agent = TravelAgent(settings=settings, demonstrate_recovery=args.demonstrate_recovery)
    result = agent.run(raw)
    output = args.output or ROOT / "results" / f"{agent.trace.data['run_id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2) + "\n")
    print(f"[{result.status}] [{settings.data_mode}] {result.message}")
    print(f"SerpApi searches: {result.serpapi_requests}; cache hits: {result.provider_cache_hits}")
    if result.budget_estimate and result.status == "infeasible":
        print("Minimum simulated costs:")
        for name in ["flights", "accommodation", "food", "activities", "local_transport"]:
            print(
                f"  {name.replace('_', ' ').title()}: EUR {getattr(result.budget_estimate, name):.2f}"
            )
    if result.ai_fallback:
        advice = result.ai_fallback
        print(
            f"\nAI BACKUP — unverified suggestions; model {advice.model}; {advice.duration_seconds:.1f}s; tokens {advice.usage.total_tokens}"
        )
        if advice.content:
            print(advice.content.summary)
            for day in advice.content.days:
                print(f"{display_date(day.date)}: {day.title}")
                for suggestion in day.suggestions:
                    print(f"  - {suggestion}")
        else:
            print(advice.error)
    if result.itinerary:
        plan = result.itinerary
        summary = plan.trip_summary
        print(
            f"{summary.origin} → {summary.destination} | {display_date(summary.start_date)} – {display_date(summary.end_date)} | {summary.travelers} traveler(s)"
        )
        for key, value in plan.budget_breakdown.model_dump().items():
            print(f"{key.replace('_', ' ').title()}: EUR {value:.2f}")
        for day in plan.daily_itinerary:
            print(f"\n{display_date(day.date)}: {day.title}")
            for slot in day.schedule:
                print(
                    f"  {slot.start_time:%H:%M}–{slot.end_time:%H:%M} {slot.meal or 'visit'}: {slot.activity.name}"
                )
    print(f"Final JSON: {output}\nExecution trace: {agent.trace.path}")
    return 0 if result.status == "success" else 2 if result.status == "needs_clarification" else 1


if __name__ == "__main__":
    raise SystemExit(main())
