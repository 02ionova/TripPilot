"""Inspect the two submitted genuine traces locally; no model or HTTP requests."""

import json
from decimal import Decimal
from pathlib import Path

from schemas import FinalResponse

ROOT = Path(__file__).resolve().parent
SUBMITTED_TRACES = (
    ROOT / "traces/20261124T205633_19e1ba5b-0276-4169-b7f3-4944c8c82099.json",
    ROOT / "traces/20261124T205633_30127e40-3f4e-4b19-9f70-b3131cb94ac1.json",
)
REQUIRED_TOOLS = {
    "get_weather",
    "search_flights",
    "search_hotels",
    "search_activities",
    "search_restaurants",
    "build_itinerary",
}
COST_CATEGORIES = ("flights", "accommodation", "food", "activities", "local_transport")


def inspect_trace(path: Path) -> dict:
    """Check saved evidence consistency, without claiming fresh availability."""
    trace = json.loads(path.read_text())
    if trace.get("execution_mode") != "real_llm" or trace.get("data_mode") != "live":
        raise ValueError("Submission evidence must be a genuine Live run.")
    result = FinalResponse.model_validate(trace["final_response"])
    if result.status != "success" or trace.get("final_status") != "success":
        raise ValueError("Submitted run must have terminated successfully.")
    plan = result.itinerary
    budget = plan.budget_breakdown
    total = Decimal(str(budget.total))
    recomputed = sum((Decimal(str(getattr(budget, key))) for key in COST_CATEGORIES), Decimal(0))
    item_total = sum((Decimal(str(item.amount)) for item in plan.cost_items), Decimal(0))
    original = Decimal(str(trace["request"]["budget"]))
    if recomputed != total or item_total != total:
        raise ValueError("Recorded expense totals do not agree.")
    if total > original or Decimal(str(budget.remaining_budget)) != original - total:
        raise ValueError("Submission example must respect its original budget.")
    if not trace.get("budget_validation", {}).get("valid"):
        raise ValueError("Trace must include successful budget validation.")
    calls = [e for e in trace["events"] if e.get("kind") == "tool_call"]
    successful = {e["tool"] for e in calls if e["result"]["status"] == "ok"}
    if not REQUIRED_TOOLS.issubset(successful) or any(not e.get("tool_call_id") for e in calls):
        raise ValueError("Missing successful tools or preserved tool-call IDs.")
    recovered = []
    for index, event in enumerate(calls):
        if event["result"]["status"] != "ok" and any(
            later["tool"] == event["tool"] and later["result"]["status"] == "ok"
            for later in calls[index + 1 :]
        ):
            recovered.append(f"{event['tool']}: {event['result']['error']['code']}")
    if "Paris" in plan.trip_summary.destination and not any(
        "search_hotels: no_priced_hotels" == error for error in recovered
    ):
        raise ValueError("Paris evidence must demonstrate actual hotel-search recovery.")
    return {
        "run_id": trace["run_id"],
        "destination": plan.trip_summary.destination,
        "iterations": len(trace["iterations"]),
        "tools": len(successful),
        "total": str(total),
        "budget": str(original),
        "recovered": recovered,
    }


def main() -> int:
    try:
        reports = [inspect_trace(path) for path in SUBMITTED_TRACES]
        if len({report["run_id"] for report in reports}) != 2:
            raise ValueError("Two distinct successful runs are required.")
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print(f"Submission verification failed: {exc}")
        return 1
    for report in reports:
        print(
            f"PASS {report['destination']}: {report['iterations']} iterations, "
            f"{report['tools']} tools, EUR {report['total']} / {report['budget']}"
        )
        print("  Recovered: " + "; ".join(report["recovered"]))
    print("Two distinct successful Live traces verified. No API requests made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
