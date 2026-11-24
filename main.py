"""CLI independent of Streamlit: python main.py --input examples/rome.json."""

import argparse
import json
from pathlib import Path

from agent import TravelAgent
from config import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="TripPilot AI — simulated travel planning")
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
    agent = TravelAgent(demonstrate_recovery=args.demonstrate_recovery)
    result = agent.run(raw)
    output = args.output or ROOT / "results" / f"{agent.trace.data['run_id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2) + "\n")
    print(f"[{result.status}] {result.message}")
    if result.budget_estimate and result.status == "infeasible":
        print("Minimum simulated costs:")
        for name in ["flights", "accommodation", "food", "activities", "local_transport"]:
            print(
                f"  {name.replace('_', ' ').title()}: EUR {getattr(result.budget_estimate, name):.2f}"
            )
    if result.itinerary:
        plan = result.itinerary
        summary = plan.trip_summary
        print(
            f"{summary.origin} → {summary.destination} | {summary.start_date} – {summary.end_date} | {summary.travelers} traveler(s)"
        )
        for key, value in plan.budget_breakdown.model_dump().items():
            print(f"{key.replace('_', ' ').title()}: EUR {value:.2f}")
        for day in plan.daily_itinerary:
            print(f"\n{day.date}: {day.title}")
            for slot in day.schedule:
                print(
                    f"  {slot.start_time:%H:%M}–{slot.end_time:%H:%M} {slot.meal or 'visit'}: {slot.activity.name}"
                )
    print(f"Final JSON: {output}\nExecution trace: {agent.trace.path}")
    return 0 if result.status == "success" else 2 if result.status == "needs_clarification" else 1


if __name__ == "__main__":
    raise SystemExit(main())
