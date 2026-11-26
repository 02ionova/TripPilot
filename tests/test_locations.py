"""Country-qualified geocoding regressions; all HTTP is mocked."""

import httpx
import pytest

from config import Settings
from providers.http import ProviderClient
from providers.locations import geocode
from tools.common import ToolFailure


def place(name, country, code, admin, population, latitude):
    return dict(
        name=name,
        country=country,
        country_code=code,
        admin1=admin,
        population=population,
        latitude=latitude,
        longitude=4.89,
    )


def geo_client(tmp_path, records):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        # Reproduce the actual provider: a valid combined country label is empty.
        return httpx.Response(
            200, json={"results": [] if "," in request.url.params["name"] else records}
        )

    return ProviderClient(
        Settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        cache_path=tmp_path / "cache.sqlite",
    ), calls


def test_amsterdam_netherlands_falls_back_and_reuses_cache(tmp_path):
    client, calls = geo_client(
        tmp_path,
        [
            place("Amsterdam", "United States", "US", "New York", 18000, 42.9),
            place("Amsterdam", "The Netherlands", "NL", "North Holland", 900000, 52.37),
            place("Amsterdam-Zuid", "The Netherlands", "NL", "North Holland", 1200000, 52.34),
        ],
    )
    city = geocode(client, "Amsterdam, Netherlands")
    assert city["country_code"] == "NL" and city["name"] == "Amsterdam"
    assert len(calls) == 2 and calls[1]["name"] == "Amsterdam"
    assert geocode(client, "Amsterdam, Netherlands") == city
    assert len(calls) == 2 and client.serpapi_requests == 0


def test_geocoding_never_drops_incorrect_country(tmp_path):
    client, _ = geo_client(
        tmp_path, [place("Amsterdam", "The Netherlands", "NL", "North Holland", 900000, 52.37)]
    )
    with pytest.raises(ToolFailure) as exc:
        geocode(client, "Amsterdam, Italy")
    assert exc.value.error.code == "city_not_found"


def test_country_and_administrative_region_are_both_respected(tmp_path):
    client, _ = geo_client(
        tmp_path,
        [
            place("Springfield", "United States", "US", "Massachusetts", 200000, 42),
            place("Springfield", "United States", "US", "Illinois", 100000, 39),
        ],
    )
    assert geocode(client, "Springfield, Illinois, US")["admin1"] == "Illinois"
    with pytest.raises(ToolFailure) as exc:
        geocode(client, "Springfield, US")
    assert exc.value.error.code == "ambiguous_city"
