"""Tests du client TollGuru avec cache SQLite."""

import httpx
import pytest
import respx

from route_compare.cost.tollguru import TollGuruClient, _cache_key, _downsample

COORDS = [[6.12, 45.90], [4.83, 45.76], [2.35, 48.85], [-2.25, 47.00]]

TOLLGURU_OK = {
    "route": {
        "costs": {"tagAndCash": 15.50, "minimumTollCost": 14.00},
        "hasTolls": True,
    }
}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    from route_compare.config import Settings
    mock_settings = Settings(tollguru_api_key="tg_test_key", storage_dir=str(tmp_path))
    monkeypatch.setattr("route_compare.cost.tollguru.settings", mock_settings)
    c = TollGuruClient()
    await c.setup()
    yield c
    await c.aclose()


@pytest.mark.asyncio
async def test_get_toll_cost_ok(client):
    with respx.mock:
        respx.post(
            "https://apis.tollguru.com/toll/v2/complete-polyline-from-mapping-service"
        ).mock(return_value=httpx.Response(200, json=TOLLGURU_OK))
        cost, confidence = await client.get_toll_cost(COORDS)
    assert cost == pytest.approx(15.50)
    assert confidence == "exact"


@pytest.mark.asyncio
async def test_get_toll_cost_api_error_fallback(client):
    with respx.mock:
        respx.post(
            "https://apis.tollguru.com/toll/v2/complete-polyline-from-mapping-service"
        ).mock(return_value=httpx.Response(500, text="error"))
        cost, confidence = await client.get_toll_cost(COORDS)
    assert cost == 0.0
    assert confidence == "estimated"


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_api_call(client):
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=TOLLGURU_OK)

    with respx.mock:
        respx.post(
            "https://apis.tollguru.com/toll/v2/complete-polyline-from-mapping-service"
        ).mock(side_effect=handler)
        await client.get_toll_cost(COORDS)
        await client.get_toll_cost(COORDS)  # doit venir du cache mémoire

    assert call_count == 1, "L'API ne doit être appelée qu'une fois pour la même route"


@pytest.mark.asyncio
async def test_sqlite_cache_survives_restart(tmp_path, monkeypatch):
    from route_compare.config import Settings
    mock_settings = Settings(tollguru_api_key="tg_test_key", storage_dir=str(tmp_path))
    monkeypatch.setattr("route_compare.cost.tollguru.settings", mock_settings)

    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=TOLLGURU_OK)

    with respx.mock:
        respx.post(
            "https://apis.tollguru.com/toll/v2/complete-polyline-from-mapping-service"
        ).mock(side_effect=handler)

        c1 = TollGuruClient()
        await c1.setup()
        await c1.get_toll_cost(COORDS)
        await c1.aclose()

        # Nouveau client — même db, l'API ne doit PAS être rappelée
        c2 = TollGuruClient()
        await c2.setup()
        cost, confidence = await c2.get_toll_cost(COORDS)
        await c2.aclose()

    assert call_count == 1, "SQLite cache doit éviter un 2e appel API après restart"
    assert cost == pytest.approx(15.50)
    assert confidence == "exact"


def test_cache_key_stable():
    k1 = _cache_key(COORDS)
    k2 = _cache_key(COORDS)
    assert k1 == k2


def test_cache_key_different_routes():
    other = [[1.0, 2.0], [3.0, 4.0]]
    assert _cache_key(COORDS) != _cache_key(other)


def test_downsample_short():
    assert _downsample(COORDS, 100) == COORDS


def test_downsample_long():
    many = [[float(i), float(i)] for i in range(1000)]
    result = _downsample(many, 100)
    assert len(result) == 100
