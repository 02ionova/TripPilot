"""Validated inputs, tool contracts and final itinerary models (EUR only)."""

from datetime import date, time
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class DateRange(Model):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def dates_valid(self):
        if not 0 <= (self.end_date - self.start_date).days <= 13:
            raise ValueError("Trip must last 1–14 calendar days, with end_date >= start_date.")
        if self.start_date.year < 2026 or self.end_date.year > 2035:
            raise ValueError("Simulated dates are supported from 2026 through 2035.")
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
    dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free"]] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def departure_not_in_past(self):
        if self.start_date < current_date():
            raise ValueError("Start date cannot be before today.")
        return self

    @field_validator("origin", "destination")
    @classmethod
    def normalize_city(cls, value):
        return value.title()

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

    @model_validator(mode="after")
    def valid_dates(self):
        DateRange(start_date=self.check_in, end_date=self.check_out)
        return self


class ActivityArgs(Model):
    destination: str = Field(min_length=1)
    interests: list[str] = Field(default_factory=list)
    dietary_preferences: list[Literal["vegetarian", "vegan", "gluten-free"]] = Field(
        default_factory=list
    )
    environment: Literal["indoor", "outdoor", "any"] = "any"
    max_price: float | None = Field(default=None, ge=0, description="Maximum price per person.")


class WeatherDay(Model):
    date: date
    min_temperature: int
    max_temperature: int
    conditions: str
    rain_probability: float = Field(ge=0, le=1)
    recommendation: Literal["indoor", "outdoor"]


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


class Hotel(Model):
    id: str
    name: str
    accommodation_type: Literal["hotel", "budget", "hostel"]
    price_per_night: float
    nights: int
    rooms: int
    total_cost: float
    neighborhood: str
    rating: float


class Activity(Model):
    id: str
    name: str
    category: Literal["attraction", "meal"]
    description: str
    interests: list[str]
    duration_minutes: int
    price_per_person: float
    environment: Literal["indoor", "outdoor"]
    dietary_compatibility: list[str]


class ToolError(Model):
    code: str
    message: str
    suggestions: list[str]


T = TypeVar("T")


class ToolResult(Model, Generic[T]):
    status: Literal["ok", "error"]
    data: T | None = None
    error: ToolError | None = None
    data_source: Literal["simulated"] = "simulated"


class ScheduledSelection(Model):
    activity_id: str
    start_time: time
    end_time: time
    meal: Literal["breakfast", "lunch", "dinner"] | None = None


class DaySelection(Model):
    date: date
    title: str = Field(min_length=1)
    schedule: list[ScheduledSelection]


class BuildArgs(Model):
    request: TravelRequest
    flight_id: str
    hotel_id: str
    days: list[DaySelection]


class ScheduledActivity(Model):
    activity: Activity
    start_time: time
    end_time: time
    meal: Literal["breakfast", "lunch", "dinner"] | None
    total_cost: float


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
    remaining_budget: float = Field(ge=0)

    @model_validator(mode="after")
    def sums_match(self):
        expected = sum(
            [self.flights, self.accommodation, self.food, self.activities, self.local_transport]
        )
        if abs(self.total - expected) > 0.005:
            raise ValueError("Budget components must sum to total.")
        return self


class TripSummary(Model):
    origin: str
    destination: str
    start_date: date
    end_date: date
    travelers: int
    currency: Literal["EUR"] = "EUR"


class Itinerary(Model):
    trip_summary: TripSummary
    selected_flights: Flight
    selected_accommodation: Hotel
    daily_itinerary: list[ItineraryDay]
    budget_breakdown: BudgetBreakdown
    weather_summary: list[WeatherDay]
    recommendations: list[str]
    warnings: list[str]
    data_source: Literal["simulated"] = "simulated"


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


class FinalResponse(Model):
    status: Literal["success", "needs_clarification", "infeasible", "error", "iteration_limit"]
    message: str
    itinerary: Itinerary | None = None
    budget_estimate: BudgetEstimate | None = None
    data_source: Literal["simulated"] = "simulated"

    @model_validator(mode="after")
    def success_requires_itinerary(self):
        if (self.status == "success") != (self.itinerary is not None):
            raise ValueError("Only success must contain a validated itinerary.")
        return self
