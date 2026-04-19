"""Client Graphhopper async avec gestion du cache et des erreurs métier."""

import hashlib
import json
from collections import OrderedDict
from typing import Any

import httpx
import structlog

from route_compare.config import settings

log = structlog.get_logger()

GRAPHHOPPER_BASE = "https://graphhopper.com/api/1"


class GraphhopperError(Exception):
    """Erreur métier Graphhopper."""


class RouteNotFoundError(GraphhopperError):
    """Le point de départ ou d'arrivée n'est pas routable."""


class QuotaExceededError(GraphhopperError):
    """Quota API dépassé."""


class GraphhopperClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)
        self._cache: OrderedDict[str, Any] = OrderedDict()

    async def geocode(self, query: str) -> tuple[float, float]:
        """Retourne (lat, lng) pour une adresse."""
        params = {
            "q": query,
            "limit": 1,
            "locale": "fr",
            "key": settings.graphhopper_api_key,
        }
        resp = await self._client.get(f"{GRAPHHOPPER_BASE}/geocode", params=params)
        self._raise_for_status(resp)
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            raise RouteNotFoundError(f"Adresse non trouvée : {query!r}")
        pt = hits[0]["point"]
        return pt["lat"], pt["lng"]

    async def route(
        self,
        points: list[tuple[float, float]],
        custom_model: dict,
        vehicle: str = "car",
    ) -> dict:
        """
        Lance un calcul d'itinéraire Graphhopper.

        Retourne le premier itinéraire (paths[0]) ou lève une exception.
        Utilise un cache en mémoire (LRU, taille configurable).
        """
        cache_key = self._cache_key(points, custom_model, vehicle)
        if cache_key in self._cache:
            log.debug("graphhopper.cache_hit", key=cache_key[:8])
            return self._cache[cache_key]

        payload = {
            "points": [[lng, lat] for lat, lng in points],
            "profile": vehicle,
            "custom_model": custom_model,
            "ch.disable": True,  # requis pour custom_model
            "points_encoded": False,
            "details": ["road_class", "toll", "max_speed"],
            "instructions": False,
        }

        if not settings.graphhopper_api_key:
            raise GraphhopperError("GRAPHHOPPER_API_KEY non configurée")

        resp = await self._client.post(
            f"{GRAPHHOPPER_BASE}/route",
            json=payload,
            params={"key": settings.graphhopper_api_key},
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_status(resp)

        data = resp.json()
        paths = data.get("paths", [])
        if not paths:
            raise RouteNotFoundError("Aucun itinéraire trouvé entre ces deux points")

        result = paths[0]
        self._store_cache(cache_key, result)
        return result

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 200:
            return
        if resp.status_code == 401:
            raise GraphhopperError("Clé API Graphhopper invalide (401)")
        if resp.status_code == 429:
            raise QuotaExceededError("Quota Graphhopper dépassé (429). Réessayez demain.")
        try:
            body = resp.json()
            message = body.get("message", resp.text)
        except Exception:
            message = resp.text
        if "Cannot find point" in message or "cannot find closestEdge" in message.lower():
            raise RouteNotFoundError(
                "Un des points n'est pas accessible par la route. "
                "Vérifiez les adresses saisies."
            )
        raise GraphhopperError(f"Erreur Graphhopper {resp.status_code} : {message}")

    def _cache_key(
        self, points: list[tuple[float, float]], custom_model: dict, vehicle: str
    ) -> str:
        data = json.dumps(
            {"points": points, "model": custom_model, "vehicle": vehicle}, sort_keys=True
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def _store_cache(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = value
            if len(self._cache) > settings.cache_max_size:
                self._cache.popitem(last=False)

    async def aclose(self) -> None:
        await self._client.aclose()
