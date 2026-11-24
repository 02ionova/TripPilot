"""Preference matching; restaurants always considered alongside attractions."""

from schemas import Activity, ActivityArgs
from tools.common import load, no_results, success


def search_activities(args: ActivityArgs):
    result = []
    interests = {x.lower() for x in args.interests}
    for raw in load("activities", args.destination):
        option = Activity(**raw)
        if args.max_price is not None and option.price_per_person > args.max_price:
            continue
        if option.category == "meal":
            if not set(args.dietary_preferences).issubset(option.dietary_compatibility):
                continue
        else:
            if interests and not interests.intersection(option.interests):
                continue
            if args.environment != "any" and option.environment != args.environment:
                continue
        result.append(option)
    if not result:
        no_results("No matching activities or meals. Broaden interests or increase the price cap.")
    return success(result)
