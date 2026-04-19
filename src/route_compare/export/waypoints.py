"""
Extraction des grandes villes traversées par un itinéraire.

Algorithme :
1. Échantillonner des points tous les ~100 km
2. Reverse geocoding via Nominatim (avec cache SQLite + rate-limit 1 req/s)
3. Filtrer par population > 30 000 ou importance > 0.5
4. Dédoublonner et limiter à 6 villes

Cache SQLite stocké dans /storage/city_cache.db.
"""

import asyncio
import math
import os
import sqlite3
from typing import Any

import httpx
import structlog

from route_compare.config import settings
from route_compare.models import WaypointCity

log = structlog.get_logger()

NOMINATIM_BASE = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "route-compare/1.0 (contact@florent.cc)"
MIN_POPULATION = 30_000
MIN_IMPORTANCE = 0.5
MAX_CITIES = 6

_nominatim_semaphore = asyncio.Semaphore(1)
_last_request_time: float = 0.0


def _db_path() -> str:
    return os.path.join(settings.storage_dir, "city_cache.db")


def _init_db() -> None:
    os.makedirs(settings.storage_dir, exist_ok=True)
    conn = sqlite3.connect(_db_path())
    conn.execute(
        """CREATE TABLE IF NOT EXISTS city_cache (
            lat_r REAL NOT NULL,
            lng_r REAL NOT NULL,
            name TEXT,
            population INTEGER,
            importance REAL,
            PRIMARY KEY (lat_r, lng_r)
        )"""
    )
    conn.commit()
    conn.close()


def _round2(v: float) -> float:
    return round(v, 2)


def _cache_lookup(lat: float, lng: float) -> dict[str, Any] | None:
    try:
        conn = sqlite3.connect(_db_path())
        row = conn.execute(
            "SELECT name, population, importance FROM city_cache WHERE lat_r=? AND lng_r=?",
            (_round2(lat), _round2(lng)),
        ).fetchone()
        conn.close()
        if row:
            return {"name": row[0], "population": row[1], "importance": row[2]}
    except Exception:
        pass
    return None


def _cache_store(lat: float, lng: float, name: str, population: int, importance: float) -> None:
    try:
        conn = sqlite3.connect(_db_path())
        conn.execute(
            "INSERT OR REPLACE INTO city_cache"
            " (lat_r, lng_r, name, population, importance) VALUES (?,?,?,?,?)",
            (_round2(lat), _round2(lng), name, population, importance),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.warning("city_cache.write_error", error=str(exc))


async def _nominatim_reverse(lat: float, lng: float) -> dict[str, Any] | None:
    """Appel Nominatim avec rate-limit 1 req/s."""
    global _last_request_time
    async with _nominatim_semaphore:
        now = asyncio.get_event_loop().time()
        wait = 1.0 - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = asyncio.get_event_loop().time()

        params = {
            "lat": str(lat),
            "lon": str(lng),
            "zoom": "10",
            "format": "json",
            "extratags": "1",
            "addressdetails": "0",
        }
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT}, timeout=10.0
            ) as client:
                resp = await client.get(NOMINATIM_BASE, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("nominatim.error", lat=lat, lng=lng, error=str(exc))
            return None


async def _resolve_city(lat: float, lng: float) -> tuple[str, int, float] | None:
    """Retourne (nom, population, importance) ou None si pas une grande ville."""
    cached = _cache_lookup(lat, lng)
    if cached is not None:
        if cached["name"] is None:
            return None
        return cached["name"], cached["population"] or 0, cached["importance"] or 0.0

    data = await _nominatim_reverse(lat, lng)
    if not data:
        _cache_store(lat, lng, "", 0, 0.0)  # type: ignore[arg-type]
        return None

    name = (
        data.get("name")
        or data.get("address", {}).get("city")
        or data.get("address", {}).get("town")
        or ""
    )
    extratags = data.get("extratags") or {}
    try:
        population = int(extratags.get("population", 0) or 0)
    except (ValueError, TypeError):
        population = 0
    importance = float(data.get("importance") or 0.0)

    if not name:
        _cache_store(lat, lng, "", population, importance)  # type: ignore[arg-type]
        return None

    _cache_store(lat, lng, name, population, importance)

    if population >= MIN_POPULATION or importance >= MIN_IMPORTANCE:
        return name, population, importance
    return None


def _sample_points(
    coords: list[list[float]], total_distance_km: float, interval_km: float = 100.0
) -> list[tuple[float, float]]:
    """
    Retourne des points échantillonnés tous les interval_km le long du tracé.
    coords : liste de [lng, lat]
    """
    if total_distance_km < interval_km:
        mid = coords[len(coords) // 2]
        return [(mid[1], mid[0])]

    n = max(1, int(total_distance_km / interval_km))
    step = len(coords) / n
    return [(coords[int(i * step)][1], coords[int(i * step)][0]) for i in range(1, n)]


async def extract_waypoint_cities(
    coords: list[list[float]],
    total_distance_km: float,
) -> list[WaypointCity]:
    """Point d'entrée principal : retourne les grandes villes traversées."""
    try:
        _init_db()
    except Exception as exc:
        log.warning("city_cache.init_error", error=str(exc))

    sample = _sample_points(coords, total_distance_km)

    results: list[WaypointCity] = []
    seen_names: set[str] = set()

    for lat, lng in sample:
        city_info = await _resolve_city(lat, lng)
        if city_info is None:
            continue
        name, _, _ = city_info
        if name in seen_names:
            continue
        seen_names.add(name)
        results.append(WaypointCity(name=name, lat=lat, lng=lng))
        if len(results) >= MAX_CITIES:
            break

    return results


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
