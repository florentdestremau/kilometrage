from route_compare.export.deep_links import apple_maps_url, google_maps_url, waze_url
from route_compare.models import Coord

DEST = Coord(lat=47.0, lng=-2.2)
ORIGIN = Coord(lat=45.9, lng=6.1)


def test_waze_url():
    url = waze_url(DEST)
    assert "waze.com/ul" in url
    assert "47.0" in url
    assert "-2.2" in url
    assert "navigate=yes" in url


def test_google_maps_url_basic():
    url = google_maps_url(ORIGIN, DEST)
    assert "google.com/maps" in url
    assert "45.9" in url
    assert "47.0" in url
    assert "driving" in url


def test_google_maps_url_avoid_tolls():
    url = google_maps_url(ORIGIN, DEST, avoid=["tolls"])
    assert "avoid=tolls" in url


def test_google_maps_url_avoid_multiple():
    url = google_maps_url(ORIGIN, DEST, avoid=["tolls", "highways"])
    assert "tolls" in url
    assert "highways" in url


def test_apple_maps_url():
    url = apple_maps_url(DEST)
    assert "maps.apple.com" in url
    assert "47.0" in url
    assert "-2.2" in url
