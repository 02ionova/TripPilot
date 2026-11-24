"""Per-run trusted result store. Building an itinerary performs no provider requests."""

from cities import bind_city_label
from providers.arrange import arrange
from providers.http import ProviderClient
from providers.itinerary import build_live_itinerary
from providers.places import places
from providers.travel import flights, hotels
from providers.weather import weather
from schemas import Activity, Flight, Hotel, ToolResult, TravelRequest, WeatherDay
from tools.common import ToolFailure
from tracing import now


class LiveTools:
    def __init__(
        self, request: TravelRequest, settings, on_event=None, http_client=None, cache_path=None
    ):
        self.request = request
        self.settings = settings
        self.client = ProviderClient(settings, on_event, http_client, cache_path)
        self.flights: dict[str, tuple[Flight, object]] = {}
        self.hotels: dict[str, tuple[Hotel, object]] = {}
        self.activities: dict[str, tuple[Activity, str]] = {}
        self.weather: dict[tuple[str, object], WeatherDay] = {}

    def bind_arguments(self, args):
        try:
            updates = {"destination": bind_city_label(args.destination, self.request.destination)}
            if hasattr(args, "origin"):
                updates["origin"] = bind_city_label(args.origin, self.request.origin)
        except ValueError:
            raise ToolFailure(
                "request_mismatch",
                "Use the cities/countries explicitly selected by the user.",
                [
                    "Country qualifiers already supplied by the user can be omitted, but a different location cannot be substituted."
                ],
            ) from None
        return args.model_copy(update=updates)

    def result(self, data, notes=None, next_page_token=None):
        return ToolResult(
            status="ok",
            data=data,
            data_source="live",
            notes=notes or [],
            retrieved_at=now(),
            next_page_token=next_page_token,
        )

    def get_weather(self, args):
        args = self.bind_arguments(args)
        result = weather(self.client, args)
        for day in result:
            self.weather[(args.destination, day.date)] = day
        return self.result(result)

    def search_flights(self, args):
        args = self.bind_arguments(args)
        result, notes = flights(self.client, args)
        for item in result:
            self.flights[item.id] = (item, args)
        return self.result(result, notes)

    def search_hotels(self, args):
        args = self.bind_arguments(args)
        result, next_page = hotels(self.client, args)
        for item in result:
            self.hotels[item.id] = (item, args)
        return self.result(
            result,
            ["No overnight stay is needed for these dates."] if not result else [],
            next_page,
        )

    def search_activities(self, args):
        args = self.bind_arguments(args)
        result = places(self.client, args)
        for item in result:
            self.activities[item.id] = (item, args.destination)
        return self.result(result)

    def search_restaurants(self, args):
        args = self.bind_arguments(args)
        args = args.model_copy(
            update={
                "dietary_preferences": list(
                    dict.fromkeys(self.request.dietary_preferences + args.dietary_preferences)
                )
            }
        )
        result = places(self.client, args, restaurants=True)
        for item in result:
            self.activities[item.id] = (item, args.destination)
        return self.result(result)

    def build_itinerary(self, args):
        if args.auto_schedule:
            args = arrange(self, args)
        result = build_live_itinerary(self, args)
        return self.result(result)
