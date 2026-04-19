"""Tests de l'endpoint /compare via TestClient FastAPI."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from route_compare.main import app

GEOCODE_ANNECY = {"hits": [{"point": {"lat": 45.899, "lng": 6.129}}]}
GEOCODE_NOIRMOUTIER = {"hits": [{"point": {"lat": 47.003, "lng": -2.249}}]}

ROUTE_RESPONSE = {
    "paths": [
        {
            "distance": 600_000.0,
            "time": 21_600_000,
            "points": {
                "type": "LineString",
                "coordinates": [[6.12, 45.90], [2.35, 48.85], [-2.25, 47.00]],
            },
            "details": {
                "road_class": [[0, 2, "MOTORWAY"]],
                "toll": [[0, 1, "ALL"], [1, 2, "NO"]],
                "max_speed": [[0, 2, 110]],
            },
        }
    ]
}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/up")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_compare_success(client):
    with respx.mock:
        # Géocodage
        respx.get("https://graphhopper.com/api/1/geocode").mock(
            side_effect=[
                httpx.Response(200, json=GEOCODE_ANNECY),
                httpx.Response(200, json=GEOCODE_NOIRMOUTIER),
            ]
        )
        # Routes (3 presets)
        respx.post("https://graphhopper.com/api/1/route").mock(
            return_value=httpx.Response(200, json=ROUTE_RESPONSE)
        )
        # Nominatim (waypoints) — retourne une ville générique
        respx.get("https://nominatim.openstreetmap.org/reverse").mock(
            return_value=httpx.Response(200, json={
                "name": "Lyon",
                "importance": 0.8,
                "extratags": {"population": "500000"},
            })
        )

        resp = client.post("/compare", json={
            "origin": "Annecy",
            "destination": "Noirmoutier",
            "max_speed": 110,
            "fuel_consumption_l_per_100": 6.5,
            "fuel_price": 1.75,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "routes" in data
    assert len(data["routes"]) > 0
    route = data["routes"][0]
    assert route["distance_km"] > 0
    assert route["cost"]["total_eur"] > 0
    assert "export" in route


def test_compare_invalid_speed(client):
    resp = client.post("/compare", json={
        "origin": "Paris",
        "destination": "Lyon",
        "max_speed": 200,  # invalide (> 130)
    })
    assert resp.status_code == 422
