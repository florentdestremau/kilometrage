"""Génération d'URLs de navigation vers Waze, Google Maps et Apple Plans."""

from urllib.parse import urlencode

from route_compare.models import Coord


def waze_url(destination: Coord) -> str:
    params = urlencode({"ll": f"{destination.lat},{destination.lng}", "navigate": "yes"})
    return f"https://www.waze.com/ul?{params}"


def google_maps_url(
    origin: Coord,
    destination: Coord,
    avoid: list[str] | None = None,
) -> str:
    params: dict[str, str] = {
        "api": "1",
        "origin": f"{origin.lat},{origin.lng}",
        "destination": f"{destination.lat},{destination.lng}",
        "travelmode": "driving",
    }
    if avoid:
        params["avoid"] = "|".join(avoid)
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def apple_maps_url(destination: Coord) -> str:
    params = urlencode({"daddr": f"{destination.lat},{destination.lng}", "dirflg": "d"})
    return f"https://maps.apple.com/?{params}"
