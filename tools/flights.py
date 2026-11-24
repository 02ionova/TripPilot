"""Simulated round trips; all times local and no overnight legs."""

from schemas import Flight, FlightArgs
from tools.common import ToolFailure, load, no_results, success


def search_flights(args: FlightArgs):
    options = load("flights", args.destination)
    if args.origin.strip().title() != "Prague":
        raise ToolFailure(
            "unsupported_origin", "Only Prague departures are supported.", ["Use Prague as origin."]
        )
    result = []
    for option in options:
        total = round(option["price_per_traveler"] * args.travelers, 2)
        if args.max_price is None or total <= args.max_price:
            result.append(
                Flight(
                    **option,
                    origin="Prague",
                    destination=args.destination.title(),
                    departure_date=args.departure_date,
                    return_date=args.return_date,
                    total_price=total,
                )
            )
    if not result:
        no_results("No round trips fit the total flight price limit.")
    return success(result)
