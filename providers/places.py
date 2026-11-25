"""Real Google Maps places with explicit missing-data and cost-estimate semantics."""

import re
from urllib.parse import quote

from providers.http import ProviderClient
from providers.locations import geocode
from providers.travel import coordinates, identifier, number, safe_url, source
from schemas import Activity, ActivityArgs, PriceInfo, RestaurantArgs
from tools.common import ToolFailure


def text_blob(raw: dict) -> str:
    return " ".join(
        str(raw.get(key, ""))
        for key in ("title", "type", "types", "description", "offerings", "service_options")
    ).lower()


def places(
    client: ProviderClient, args: ActivityArgs | RestaurantArgs, *, restaurants: bool = False
) -> list[Activity]:
    city = geocode(client, args.destination)
    if args.query:
        prefix = " ".join(args.dietary_preferences) + " restaurants " if restaurants else ""
        query = f"{prefix}{args.query} in {args.destination}"
    elif restaurants:
        diets = " ".join(args.dietary_preferences)
        query = f"{diets} restaurants cafes local food in {args.destination}".strip()
    else:
        categories = {
            "architecture": "architectural landmarks",
            "museums": "museums",
            "history": "historical attractions",
            "nature": "parks nature attractions",
            "shopping": "shopping centers",
            "nightlife": "entertainment venues",
            "photography": "scenic viewpoints",
            "relaxation": "parks galleries",
            "local food": "food markets",
        }
        terms = [categories.get(i, i) for i in args.interests][:3]
        query = f"{' '.join(terms) or 'tourist attractions museums parks'} in {args.destination}"
    near = getattr(args, "near", None)
    lat = near.latitude if near else city["latitude"]
    lon = near.longitude if near else city["longitude"]
    payload = client.search("google_maps", q=query, type="search", ll=f"@{lat},{lon},13z")
    rows = payload.get("local_results", [])
    if not rows and isinstance(payload.get("place_results"), dict):
        rows = [payload["place_results"]]
    result = []
    for raw in rows:
        if not raw.get("title") or raw.get("permanently_closed") or raw.get("temporarily_closed"):
            continue
        blob = text_blob(raw)
        environment = (
            "indoor"
            if restaurants
            or any(
                word in blob
                for word in (
                    "museum",
                    "gallery",
                    "shopping mall",
                    "cathedral",
                    "church",
                    "exhibition",
                )
            )
            else "outdoor"
            if any(word in blob for word in ("park", "garden", "viewpoint", "outdoor", "square"))
            else "unknown"
        )
        if (
            not restaurants
            and args.environment != "any"
            and environment not in {args.environment, "unknown"}
        ):
            continue
        gps = raw.get("gps_coordinates", {})
        position = coordinates(gps)
        notes = []
        if restaurants:
            label = str(raw.get("price", ""))
            symbol_count = max(label.count("$"), label.count("€"), label.count("£"))
            estimate = {1: 10.0, 2: 18.0, 3: 30.0, 4: 50.0}.get(
                symbol_count, client.settings.estimated_meal_eur
            )
            euro_range = re.search(
                r"(?:€|EUR)\s*(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)", label, re.I
            )
            if euro_range:
                estimate = round(
                    (
                        float(euro_range[1].replace(",", "."))
                        + float(euro_range[2].replace(",", "."))
                    )
                    / 2,
                    2,
                )
            price = PriceInfo(
                amount=estimate,
                kind="estimated",
                basis="Per person per meal",
                notes=[
                    f"Estimated meal allowance; provider price indication: {label or 'not supplied'}. No confirmed menu quote.",
                    "Currency conversion is not inferred from dollar/pound price symbols; they are used only as cost-tier indications.",
                ],
            )
        else:
            # A price tier such as '$$' is NOT an admission fee. Only explicitly
            # EUR-denominated admission/ticket fields can count as retrieved prices.
            ticket = raw.get("admission_price") or raw.get("ticket_price")
            exact = (
                number(ticket.get("amount"))
                if isinstance(ticket, dict) and ticket.get("currency") == "EUR"
                else None
            )
            price = PriceInfo(
                amount=exact if exact is not None else client.settings.estimated_activity_eur,
                kind="retrieved" if exact is not None else "estimated",
                basis="Per person per visit",
                notes=[]
                if exact is not None
                else [
                    "Admission price is unavailable. A configurable EUR 15 planning allowance is used; this is not a quoted ticket price."
                ],
            )
        if args.max_price is not None and price.amount > args.max_price:
            continue
        compatible = [
            diet
            for diet in ("vegetarian", "vegan", "gluten-free", "halal")
            if diet in blob or diet.replace("-", " ") in blob
        ]
        if "vegan" in compatible and "vegetarian" not in compatible:
            compatible.append("vegetarian")
        if restaurants:
            notes.append(
                "Dietary suitability is only a search/provider indication, not a guarantee. Confirm with the venue, especially gluten cross-contamination and halal certification."
            )
        hours = raw.get("operating_hours", {})
        if not isinstance(hours, dict):
            hours = {}
        hours = {str(k).lower(): str(v) for k, v in hours.items() if isinstance(v, str)}
        if not hours:
            notes.append(
                "Opening hours are unavailable; verify the planned visit time with the venue."
            )
        if not position:
            notes.append("Coordinates unavailable; transfer time uses an explicit estimate.")
        place_id = raw.get("place_id")
        url = safe_url(raw.get("link")) or (
            "https://www.google.com/maps/search/?api=1&query="
            + quote(raw["title"] + " " + str(raw.get("address", "")))
            + ("&query_place_id=" + quote(place_id) if place_id else "")
        )
        result.append(
            Activity(
                id=identifier(
                    "restaurant" if restaurants else "place",
                    raw.get("data_id") or place_id or raw["title"],
                    args.destination,
                ),
                name=raw["title"],
                category="meal" if restaurants else "attraction",
                description=raw.get("description")
                or raw.get("type")
                or "Description not supplied by the provider",
                interests=getattr(args, "interests", []) or (["local food"] if restaurants else []),
                duration_minutes=45 if restaurants else 60,
                price_per_person=price.amount,
                environment=environment,
                dietary_compatibility=compatible,
                address=raw.get("address"),
                coordinates=position,
                rating=number(raw.get("rating")),
                reviews=raw.get("reviews") if isinstance(raw.get("reviews"), int) else None,
                opening_hours=hours,
                source_category=raw.get("type"),
                url=url,
                website=safe_url(raw.get("website")),
                image_url=safe_url(raw.get("thumbnail")),
                price_info=price,
                dietary_status="provider_indication" if compatible else "unverified",
                source=source(payload, "SerpApi Google Maps", url),
                notes=notes
                + [
                    "Visit/meal duration is an estimated planning allowance, not a provider-stated duration."
                ],
            )
        )
    if not result:
        raise ToolFailure(
            "no_restaurants" if restaurants else "no_activities",
            "No usable places match these filters.",
            [
                "Broaden query/environment/price filters. Unknown prices are estimates, not free admission."
            ],
        )
    return result[:12]
