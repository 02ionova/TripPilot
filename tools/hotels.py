"""Room rates for hotels/budget rooms, per-bed rates for hostels."""

from math import ceil

from schemas import Hotel, HotelArgs
from tools.common import load, no_results, success


def search_hotels(args: HotelArgs):
    result = []
    for option in load("hotels", args.destination):
        rooms = ceil(args.travelers / option["capacity"])
        nightly = option["price_per_night"] * rooms
        if args.accommodation_type and args.accommodation_type != option["accommodation_type"]:
            continue
        if args.max_nightly_price is not None and nightly > args.max_nightly_price:
            continue
        nights = (args.check_out - args.check_in).days
        result.append(
            Hotel(
                **{k: v for k, v in option.items() if k != "capacity"},
                nights=nights,
                rooms=rooms,
                total_cost=round(nightly * nights, 2),
            )
        )
    if not result:
        no_results(
            "No accommodation matches the nightly limit and type. Hostels start at EUR 23–25 per bed; hotel rooms start at EUR 85."
        )
    return success(result)
