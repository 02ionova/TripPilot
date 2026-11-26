"""Validated inputs, tool contracts and final itinerary models (EUR only)."""

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from budgeting import maximum_budget
from cities import normalize_city_name


class Model(BaseModel):
    @field_validator("origin", "destination", check_fields=False)
    @classmethod
    def valid_city_label(cls, value: str) -> str:
        return normalize_city_name(value)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class DateRange(Model):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates_valid(self):
        if not 0 <= (self.end_date - self.start_date).days <= 13:
            raise ValueError("Trip must last 1–14 calendar days, with end_date >= start_date.")
        if self.start_date.year < 2026 or self.end_date.year > 2035:
            raise ValueError("Dates are supported from 2026 through 2035.")
        return self


def current_date() -> date:
    """Local application date, evaluated on every validation and UI render."""
    return date.today()


class TravelRequest(DateRange):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    budget: float = Field(gt=0)
    travelers: int = Field(default=1, gt=0, le=20, strict=True)
    pace: Literal["relaxed", "moderate", "intensive"] = "moderate"
    interests: list[str] = Field(default_factory=list)
    dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free", "halal"]] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def departure_not_in_past(self):
        if self.origin == self.destination:
            raise ValueError("Departure and destination cities must be different.")
        if self.start_date < current_date():
            raise ValueError("Start date cannot be before today.")
        return self

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("Interests must not be blank.")
        return [value.strip().lower() for value in values]


class WeatherArgs(DateRange):
    destination: str = Field(min_length=1)


class FlightArgs(Model):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    departure_date: date
    return_date: date
    outbound_index: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Choose a different outbound candidate to explore other return options; each uncached candidate needs another request.",
    )
    max_stops: int | None = Field(default=None, ge=0, le=2)
    travelers: int = Field(gt=0, le=20, strict=True)
    max_price: float | None = Field(
        default=None, ge=0, description="Maximum total round-trip price for all travelers."
    )

    @model_validator(mode="after")
    def valid_dates(self):
        DateRange(start_date=self.departure_date, end_date=self.return_date)
        return self


class HotelArgs(Model):
    destination: str = Field(min_length=1)
    check_in: date
    check_out: date
    travelers: int = Field(gt=0, le=20, strict=True)
    max_nightly_price: float | None = Field(
        default=None, ge=0, description="Maximum combined nightly cost for all travelers."
    )
    accommodation_type: Literal["hotel", "budget", "hostel"] | None = None
    page_token: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def valid_dates(self):
        DateRange(start_date=self.check_in, end_date=self.check_out)
        return self


class ActivityArgs(Model):
    destination: str = Field(min_length=1)
    query: str | None = Field(default=None, max_length=200)
    interests: list[str] = Field(default_factory=list)
    dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free", "halal"]] = Field(
        default_factory=list
    )
    environment: Literal["indoor", "outdoor", "any"] = "any"
    max_price: float | None = Field(default=None, ge=0, description="Maximum price per person.")


class SourceInfo(Model):
    provider: str
    retrieved_at: datetime
    url: str | None = None


class PriceInfo(Model):
    amount: float = Field(ge=0)
    currency: Literal["EUR"] = "EUR"
    kind: Literal["retrieved", "estimated"]
    basis: str
    notes: list[str] = Field(default_factory=list)


class Coordinates(Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class FlightSegment(Model):
    airline: str
    flight_number: str | None = None
    departure_airport: str
    arrival_airport: str
    departure: datetime
    arrival: datetime
    duration_minutes: int | None = None


class RestaurantArgs(Model):
    destination: str = Field(min_length=1)
    dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free", "halal"]] = Field(
        default_factory=list
    )
    query: str | None = Field(default=None, max_length=200)
    near: Coordinates | None = None
    max_price: float | None = Field(default=None, ge=0)


class WeatherDay(Model):
    date: date
    min_temperature: float
    max_temperature: float
    conditions: str
    rain_probability: float | None = Field(default=None, ge=0, le=1)
    recommendation: Literal["indoor", "outdoor"]
    information_type: Literal["simulated", "Weather forecast", "Historical climate estimate"] = (
        "simulated"
    )
    wind_speed_kmh: float | None = None
    historical_years: list[int] = Field(default_factory=list)
    historical_wet_day_frequency: float | None = Field(default=None, ge=0, le=1)
    source: SourceInfo | None = None
    notes: list[str] = Field(default_factory=list)


class Flight(Model):
    id: str
    airline: str
    origin: str
    destination: str
    departure_date: date
    return_date: date
    departure_time: time
    arrival_time: time
    return_departure_time: time
    return_arrival_time: time
    duration_minutes: int
    price_per_traveler: float
    total_price: float
    outbound_segments: list[FlightSegment] = Field(default_factory=list)
    return_segments: list[FlightSegment] = Field(default_factory=list)
    outbound_arrival: datetime | None = None
    return_departure: datetime | None = None
    stops: int = 0
    return_stops: int = 0
    price_info: PriceInfo | None = None
    source: SourceInfo | None = None
    search_url: str | None = None
    notes: list[str] = Field(default_factory=list)


class Hotel(Model):
    id: str
    name: str
    accommodation_type: Literal["hotel", "budget", "hostel"]
    price_per_night: float
    nights: int
    rooms: int
    total_cost: float
    neighborhood: str
    rating: float | None
    reviews: int | None = None
    address: str | None = None
    coordinates: Coordinates | None = None
    image_url: str | None = None
    url: str | None = None
    price_info: PriceInfo | None = None
    taxes_included: bool | None = None
    quoted_adults_per_room: int | None = None
    source: SourceInfo | None = None
    notes: list[str] = Field(default_factory=list)


class Activity(Model):
    id: str
    name: str
    category: Literal["attraction", "meal"]
    description: str
    interests: list[str]
    duration_minutes: int
    price_per_person: float
    environment: Literal["indoor", "outdoor", "unknown"]
    dietary_compatibility: list[str]
    address: str | None = None
    coordinates: Coordinates | None = None
    rating: float | None = None
    reviews: int | None = None
    opening_hours: dict[str, str] = Field(default_factory=dict)
    permanently_closed: bool = False
    temporarily_closed: bool = False
    source_category: str | None = None
    url: str | None = None
    website: str | None = None
    image_url: str | None = None
    price_info: PriceInfo | None = None
    dietary_status: Literal["simulated", "provider_indication", "unverified"] = "simulated"
    source: SourceInfo | None = None
    notes: list[str] = Field(default_factory=list)


class ToolError(Model):
    code: str
    message: str
    suggestions: list[str]


T = TypeVar("T")


class ToolResult(Model, Generic[T]):
    status: Literal["ok", "error"]
    data: T | None = None
    error: ToolError | None = None
    data_source: Literal["simulated", "live"] = "simulated"
    notes: list[str] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    next_page_token: str | None = None


class ScheduledSelection(Model):
    activity_id: str
    start_time: time
    end_time: time
    meal: Literal["breakfast", "lunch", "dinner"] | None = None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def normalize_clock(cls, value):
        """Accept unambiguous H:MM from models; invalid hours still fail validation."""
        if isinstance(value, str) and re.fullmatch(r"[0-9]:[0-9]{2}", value):
            return "0" + value
        return value


class DaySelection(Model):
    date: date
    title: str = Field(min_length=1)
    schedule: list[ScheduledSelection]


class BuildArgs(Model):
    auto_schedule: bool = False
    request: TravelRequest
    flight_id: str
    hotel_id: str | None = None
    days: list[DaySelection]


class LiveBuildArgs(BuildArgs):
    auto_schedule: bool = Field(
        default=True,
        description="Let Python arrange the selected attraction IDs and fill required meals from retrieved restaurants. Proposed slot times are suggestions only in this mode. All final times, opening hours, transfers and prices are validated. Set false for strict validation of exact proposed times.",
    )


class ScheduledActivity(Model):
    activity: Activity
    start_time: time
    end_time: time
    meal: Literal["breakfast", "lunch", "dinner"] | None
    total_cost: float
    transfer_minutes: int = 0
    transfer_note: str | None = None


class ItineraryDay(Model):
    date: date
    title: str
    weather: WeatherDay
    schedule: list[ScheduledActivity]
    estimated_cost: float
    local_transport: float
    recommendations: list[str]


class BudgetBreakdown(Model):
    flights: float = Field(ge=0)
    accommodation: float = Field(ge=0)
    food: float = Field(ge=0)
    activities: float = Field(ge=0)
    local_transport: float = Field(ge=0)
    total: float = Field(ge=0)
    remaining_budget: float = Field(
        description="Original target minus total; negative for an accepted alternative up to 10% above target."
    )

    @model_validator(mode="after")
    def sums_match(self):
        expected = sum(
            [self.flights, self.accommodation, self.food, self.activities, self.local_transport]
        )
        if abs(self.total - expected) > 0.005:
            raise ValueError("Budget components must sum to total.")
        if self.remaining_budget < 0:
            target = Decimal(str(self.total)) + Decimal(str(self.remaining_budget))
            if target <= 0 or Decimal(str(self.total)) > maximum_budget(target):
                raise ValueError("Total cannot exceed the original budget by more than 10%.")
        return self


class TripSummary(Model):
    origin: str
    destination: str
    start_date: date
    end_date: date
    travelers: int
    currency: Literal["EUR"] = "EUR"


class CostItem(Model):
    category: Literal["flights", "accommodation", "food", "activities", "local_transport"]
    label: str
    amount: float = Field(ge=0)
    kind: Literal["retrieved", "estimated"]
    source: SourceInfo | None = None
    notes: list[str] = Field(default_factory=list)


class Itinerary(Model):
    trip_summary: TripSummary
    selected_flights: Flight
    selected_accommodation: Hotel | None
    daily_itinerary: list[ItineraryDay]
    budget_breakdown: BudgetBreakdown
    weather_summary: list[WeatherDay]
    recommendations: list[str]
    warnings: list[str]
    cost_items: list[CostItem] = Field(default_factory=list)
    data_source: Literal["simulated", "live"] = "simulated"


class FinalDecision(Model):
    """Small native structured LLM response; itinerary is always supplied by Python."""

    status: Literal["success", "needs_clarification", "infeasible", "error"]
    message: str


class BudgetEstimate(Model):
    """Necessary minimum catalogue costs; not a proposed or booked itinerary."""

    flights: float = Field(ge=0)
    accommodation: float = Field(ge=0)
    food: float = Field(ge=0)
    activities: float = Field(ge=0)
    local_transport: float = Field(ge=0)
    minimum_total: float = Field(ge=0)
    available_budget: float = Field(gt=0)
    shortfall: float = Field(ge=0)


class AdviceDay(Model):
    date: date
    title: str
    suggestions: list[str]


class AIAdviceContent(Model):
    """General suggestions only, never trusted offers or a validated itinerary."""

    title: str
    summary: str
    days: list[AdviceDay]
    budget_guidance: list[str]
    verification_steps: list[str]


class TokenUsage(Model):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AIAdvice(Model):
    status: Literal["available", "error"]
    reason: str
    failed_tools: list[str]
    content: AIAdviceContent | None = None
    model: str
    generated_at: datetime
    duration_seconds: float
    usage: TokenUsage = Field(default_factory=TokenUsage)
    data_source: Literal["unverified_ai"] = "unverified_ai"
    budget_validated: Literal[False] = False
    availability_verified: Literal[False] = False
    error: str | None = None


class FinalResponse(Model):
    status: Literal["success", "needs_clarification", "infeasible", "error", "iteration_limit"]
    message: str
    itinerary: Itinerary | None = None
    budget_estimate: BudgetEstimate | None = None
    ai_fallback: AIAdvice | None = None
    serpapi_requests: int = 0
    provider_cache_hits: int = 0
    retrieved_at: datetime | None = None
    data_source: Literal["simulated", "live"] = "simulated"

    @model_validator(mode="after")
    def success_requires_itinerary(self):
        if (self.status == "success") != (self.itinerary is not None):
            raise ValueError("Only success must contain a validated itinerary.")
        return self
