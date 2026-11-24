"""Normalize Google Flights/Hotels offers. Missing prices never become zero."""

import hashlib
import math
from datetime import datetime
from math import ceil

from providers.http import ProviderClient
from providers.locations import airport_id
from schemas import (
    Coordinates,
    Flight,
    FlightArgs,
    FlightSegment,
    Hotel,
    HotelArgs,
    PriceInfo,
    SourceInfo,
)
from tools.common import ToolFailure


def identifier(prefix: str, *values) -> str:
    return prefix + "-" + hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()[:16]


def number(value) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    return None


def safe_url(value: str | None) -> str | None:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return None
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query)
        if not any(word in k.lower() for word in ("api_key", "token", "authorization"))
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def coordinates(raw) -> Coordinates | None:
    if not isinstance(raw, dict):
        return None
    lat, lon = raw.get("latitude"), raw.get("longitude")
    if (
        isinstance(lat, (int, float))
        and isinstance(lon, (int, float))
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        return Coordinates(latitude=lat, longitude=lon)
    return None


def source(payload: dict, provider: str, url: str | None = None) -> SourceInfo:
    return SourceInfo(provider=provider, retrieved_at=payload["_retrieved_at"], url=safe_url(url))


def check_currency(payload: dict):
    currency = payload.get("search_parameters", {}).get("currency")
    if currency and str(currency).upper() != "EUR":
        raise ToolFailure(
            "currency_mismatch",
            "The provider returned a non-EUR quote; no exchange rate is assumed.",
            ["Retry with EUR currency or choose another source."],
        )


def segments(raw: dict) -> list[FlightSegment]:
    result = []
    for leg in raw.get("flights", []):
        dep, arr = leg.get("departure_airport", {}), leg.get("arrival_airport", {})
        try:
            result.append(
                FlightSegment(
                    airline=leg.get("airline") or "Airline not provided",
                    flight_number=leg.get("flight_number"),
                    departure_airport=dep["id"],
                    arrival_airport=arr["id"],
                    departure=datetime.fromisoformat(dep["time"]),
                    arrival=datetime.fromisoformat(arr["time"]),
                    duration_minutes=leg.get("duration"),
                )
            )
        except (KeyError, ValueError, TypeError):
            return []
    return result


def flights(client: ProviderClient, args: FlightArgs) -> tuple[list[Flight], list[str]]:
    departure = airport_id(client, args.origin)
    arrival = airport_id(client, args.destination)
    params = dict(
        departure_id=departure,
        arrival_id=arrival,
        outbound_date=str(args.departure_date),
        return_date=str(args.return_date),
        adults=args.travelers,
        currency="EUR",
        type=1,
        sort_by=2,
    )
    if args.max_stops is not None:
        params["stops"] = args.max_stops + 1
    # Do not put a price cap on the outbound request: it is reused for local
    # filtering/replanning, and only the return-selection response is a full quote.
    outgoing = client.search("google_flights", **params)
    check_currency(outgoing)
    choices = outgoing.get("best_flights", []) + outgoing.get("other_flights", [])
    if not choices or args.outbound_index >= len(choices):
        raise ToolFailure(
            "no_flights",
            "No outbound candidates match this route, date or index.",
            ["Try different dates, nearby airports, or outbound_index=0."],
        )
    chosen = choices[args.outbound_index]
    outbound = segments(chosen)
    token = chosen.get("departure_token")
    if not token or not outbound:
        raise ToolFailure(
            "incomplete_flight_offer",
            "The provider did not supply a usable return-selection token and complete outbound times.",
            [
                "Try another outbound_index; do not treat the outbound quote as a complete itinerary."
            ],
        )
    returning = client.search("google_flights", **params, departure_token=token)
    check_currency(returning)
    options = returning.get("best_flights", []) + returning.get("other_flights", [])
    link = returning.get("search_metadata", {}).get("google_flights_url") or outgoing.get(
        "search_metadata", {}
    ).get("google_flights_url")
    result = []
    for option in options:
        inbound = segments(option)
        total = number(option.get("price"))
        duration = chosen.get("total_duration")
        if not inbound or total is None or not isinstance(duration, int):
            continue
        if (
            outbound[0].departure.date() != args.departure_date
            or inbound[0].departure.date() != args.return_date
        ):
            continue
        if args.max_price is not None and total > args.max_price:
            continue
        # Price in the return-selection response is the total round-trip quote
        # for the requested passenger party. Never add the outbound price again.
        result.append(
            Flight(
                id=identifier("flight", params, chosen.get("departure_token"), inbound, total),
                airline=" / ".join(dict.fromkeys(s.airline for s in outbound + inbound)),
                origin=args.origin,
                destination=args.destination,
                departure_date=args.departure_date,
                return_date=args.return_date,
                departure_time=outbound[0].departure.time(),
                arrival_time=outbound[-1].arrival.time(),
                return_departure_time=inbound[0].departure.time(),
                return_arrival_time=inbound[-1].arrival.time(),
                duration_minutes=duration,
                price_per_traveler=round(total / args.travelers, 2),
                total_price=total,
                outbound_segments=outbound,
                return_segments=inbound,
                outbound_arrival=outbound[-1].arrival,
                return_departure=inbound[0].departure,
                stops=len(outbound) - 1,
                return_stops=len(inbound) - 1,
                price_info=PriceInfo(
                    amount=total,
                    kind="retrieved",
                    basis="Round-trip total for all requested adults",
                    notes=[
                        "The outbound preview price is not added to the complete quote.",
                        "Baggage, seats and fare conditions must be checked on the booking site.",
                    ],
                ),
                source=source(returning, "SerpApi Google Flights", link),
                search_url=safe_url(link),
                notes=[
                    "Segment timestamps are local to the named airports; provider duration is used rather than subtracting times in different time zones."
                ],
            )
        )
        if len(result) >= 4:
            break
    if not result:
        raise ToolFailure(
            "no_complete_round_trips",
            "No fully priced round trip with both leg schedules fits the current cap.",
            [
                "Increase max_price or select another outbound_index.",
                "Do not reuse a one-way or outbound-only price.",
            ],
        )
    return result, [
        f"Outbound candidate {args.outbound_index + 1} of {len(choices)} was explored. Other indexes can be requested and count toward the request cap."
    ]


def rate(raw: dict) -> tuple[float | None, bool | None]:
    after = number(raw.get("extracted_after_taxes_fees"))
    if after is not None:
        return after, True
    low = number(raw.get("extracted_lowest"))
    if low is not None:
        return low, None
    before = number(raw.get("extracted_before_taxes_fees"))
    return before, False if before is not None else None


def hotels(client: ProviderClient, args: HotelArgs) -> tuple[list[Hotel], str | None]:
    nights = (args.check_out - args.check_in).days
    if nights == 0:
        return [], None
    rooms = ceil(args.travelers / 2)
    adults = min(args.travelers, 2)
    query = f"{args.destination} accommodation"
    if args.accommodation_type:
        query = f"{args.destination} {args.accommodation_type} accommodation"
    payload = client.search(
        "google_hotels",
        q=query,
        check_in_date=str(args.check_in),
        check_out_date=str(args.check_out),
        adults=adults,
        currency="EUR",
        sort_by=3,
        next_page_token=args.page_token,
    )
    check_currency(payload)
    raw_options = payload.get("properties", [])
    if not raw_options and payload.get("property_token"):
        raw_options = [payload]
    result = []
    for option in raw_options:
        total, taxes = rate(option.get("total_rate", {}))
        nightly, _ = rate(option.get("rate_per_night", {}))
        if total is None and nightly is None:
            continue
        derived = total is None
        if total is None:
            total = round(nightly * nights, 2)
        if nightly is None:
            nightly = round(total / nights, 2)
        if args.max_nightly_price is not None and total * rooms / nights > args.max_nightly_price:
            continue
        notes = []
        if taxes is not True:
            notes.append(
                "Tax and mandatory-fee inclusion is not confirmed; extra charges may apply."
            )
        if derived:
            notes.append(
                "Total estimated from a retrieved nightly rate; nightly variation is not confirmed."
            )
        if rooms > 1:
            notes.append(
                f"Estimated group accommodation cost: one retrieved {adults}-adult room rate multiplied by {rooms} rooms. Simultaneous room inventory is not confirmed; verify before booking."
            )
        location = option.get("gps_coordinates")
        position = coordinates(location)
        images = option.get("images", [])
        image = option.get("thumbnail") or (
            images[0].get("original_image") or images[0].get("thumbnail") if images else None
        )
        kind = (
            "hostel"
            if "hostel" in (option.get("name", "") + " " + option.get("type", "")).lower()
            else "hotel"
        )
        total_group = round(total * rooms, 2)
        result.append(
            Hotel(
                id=identifier(
                    "hotel",
                    option.get("property_token") or option.get("name"),
                    args.check_in,
                    args.check_out,
                    args.travelers,
                    rooms,
                    total_group,
                ),
                name=option.get("name") or "Name not supplied",
                accommodation_type=kind,
                price_per_night=nightly,
                nights=nights,
                rooms=rooms,
                total_cost=total_group,
                neighborhood=option.get("address")
                or option.get("description")
                or "Address not provided",
                address=option.get("address"),
                rating=number(option.get("overall_rating")),
                reviews=option.get("reviews") if isinstance(option.get("reviews"), int) else None,
                coordinates=position,
                image_url=safe_url(image),
                url=safe_url(option.get("link"))
                or safe_url(payload.get("search_metadata", {}).get("google_hotels_url")),
                price_info=PriceInfo(
                    amount=total_group,
                    kind="estimated" if rooms > 1 or derived else "retrieved",
                    basis=f"{nights} nights, {rooms} room(s), {args.travelers} traveler(s)",
                    notes=notes,
                ),
                taxes_included=taxes,
                quoted_adults_per_room=adults,
                source=source(payload, "SerpApi Google Hotels", option.get("link")),
                notes=notes,
            )
        )
    if not result:
        raise ToolFailure(
            "no_priced_hotels",
            "No accommodation with a usable price fits these filters.",
            [
                "Broaden accommodation_type, increase max_nightly_price, try a hostel or another page."
            ],
        )
    return sorted(result, key=lambda h: h.total_cost)[:8], payload.get(
        "serpapi_pagination", {}
    ).get("next_page_token")
