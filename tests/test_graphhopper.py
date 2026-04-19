import httpx
import pytest
import respx

from route_compare.routing.graphhopper import (
    GraphhopperClient,
    QuotaExceededError,
    RouteNotFoundError,
)

SAMPLE_PATH = {
    "distance": 500000.0,
    "time": 18000000,
    "points": {
        "type": "LineString",
        "coordinates": [[6.12, 45.90], [2.35, 48.85]],
    },
    "details": {
        "road_class": [[0, 1, "MOTORWAY"]],
        "toll": [[0, 1, "ALL"]],
        "max_speed": [[0, 1, 130]],
    },
}

SAMPLE_ROUTE_RESPONSE = {"paths": [SAMPLE_PATH]}

SAMPLE_GEOCODE_RESPONSE = {
    "hits": [{"point": {"lat": 45.899, "lng": 6.129}}]
}


@pytest.fixture
def client():
    return GraphhopperClient()


@pytest.mark.asyncio
async def test_route_success(client):
    with respx.mock:
        respx.post("https://graphhopper.com/api/1/route").mock(
            return_value=httpx.Response(200, json=SAMPLE_ROUTE_RESPONSE)
        )
        result = await client.route([(45.90, 6.12), (48.85, 2.35)])
    assert isinstance(result, list)
    assert result[0]["distance"] == 500000.0
    await client.aclose()


@pytest.mark.asyncio
async def test_route_quota_exceeded(client):
    with respx.mock:
        respx.post("https://graphhopper.com/api/1/route").mock(
            return_value=httpx.Response(429, json={"message": "rate limit"})
        )
        with pytest.raises(QuotaExceededError):
            await client.route([(45.90, 6.12), (48.85, 2.35)])
    await client.aclose()


@pytest.mark.asyncio
async def test_route_not_found(client):
    with respx.mock:
        respx.post("https://graphhopper.com/api/1/route").mock(
            return_value=httpx.Response(400, json={"message": "Cannot find point 0: 0.0,0.0"})
        )
        with pytest.raises(RouteNotFoundError):
            await client.route([(0.0, 0.0), (48.85, 2.35)])
    await client.aclose()


@pytest.mark.asyncio
async def test_route_cache(client):
    """La même requête ne doit appeler l'API qu'une fois."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=SAMPLE_ROUTE_RESPONSE)

    with respx.mock:
        respx.post("https://graphhopper.com/api/1/route").mock(side_effect=handler)
        await client.route([(45.90, 6.12), (48.85, 2.35)])
        await client.route([(45.90, 6.12), (48.85, 2.35)])

    assert call_count == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_geocode_success(client):
    with respx.mock:
        respx.get("https://graphhopper.com/api/1/geocode").mock(
            return_value=httpx.Response(200, json=SAMPLE_GEOCODE_RESPONSE)
        )
        lat, lng = await client.geocode("Annecy")
    assert lat == pytest.approx(45.899)
    await client.aclose()


@pytest.mark.asyncio
async def test_geocode_not_found(client):
    with respx.mock:
        respx.get("https://graphhopper.com/api/1/geocode").mock(
            return_value=httpx.Response(200, json={"hits": []})
        )
        with pytest.raises(RouteNotFoundError):
            await client.geocode("ZZZ lieu inexistant ZZZ")
    await client.aclose()
