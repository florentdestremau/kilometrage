"""
Client TollGuru async avec cache SQLite persistant.

Deux niveaux de cache :
1. Mémoire (OrderedDict LRU) — évite les lectures SQLite répétées dans la même session.
2. SQLite (/storage/tollguru_cache.db) — persistant entre les redémarrages.

Clé de cache : SHA-256 des coordonnées échantillonnées et arrondies à 4 décimales.
La requête API n'est faite qu'une seule fois par géométrie de route unique.
"""

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

import aiosqlite
import httpx
import structlog

from route_compare.config import settings

log = structlog.get_logger()

TOLLGURU_URL = "https://apis.tollguru.com/toll/v2/complete-polyline-from-mapping-service"
VEHICLE_TYPE = "2AxlesAuto"
_SAMPLE_SIZE = 100   # points max envoyés à TollGuru pour limiter la taille de requête
_MEM_CACHE_MAX = 200


class TollGuruClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)
        self._mem: OrderedDict[str, float] = OrderedDict()
        self._db_path = f"{settings.storage_dir}/tollguru_cache.db"
        self._ready = False

    async def setup(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS toll_cache (
                    cache_key TEXT PRIMARY KEY,
                    toll_eur   REAL NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            await db.commit()
        self._ready = True

    async def get_toll_cost(self, coordinates: list[list[float]]) -> tuple[float, str]:
        """
        Retourne (coût_péage_eur, confidence) pour une géométrie de route.

        coordinates : [[lng, lat], ...] tel que retourné par Graphhopper.
        confidence  : "exact" si TollGuru a répondu, "estimated" si fallback.
        """
        if not settings.tollguru_api_key or not self._ready:
            return 0.0, "estimated"

        cache_key = _cache_key(coordinates)

        # 1. Mémoire
        if cache_key in self._mem:
            log.debug("tollguru.mem_hit", key=cache_key[:8])
            return self._mem[cache_key], "exact"

        # 2. SQLite
        cached = await _db_get(self._db_path, cache_key)
        if cached is not None:
            log.debug("tollguru.db_hit", key=cache_key[:8])
            self._mem_store(cache_key, cached)
            return cached, "exact"

        # 3. API TollGuru
        toll = await self._fetch(coordinates)
        if toll is None:
            return 0.0, "estimated"

        self._mem_store(cache_key, toll)
        await _db_store(self._db_path, cache_key, toll)
        return toll, "exact"

    async def _fetch(self, coordinates: list[list[float]]) -> float | None:
        # Sous-échantillonnage : on garde au max _SAMPLE_SIZE points
        sample = _downsample(coordinates, _SAMPLE_SIZE)
        # TollGuru attend [lat, lng], Graphhopper fournit [lng, lat]
        points = [[round(lat, 6), round(lng, 6)] for lng, lat in sample]

        payload: dict[str, Any] = {
            "polyline": {"type": "points", "points": points},
            "vehicle": {"type": VEHICLE_TYPE},
            "departure_time": int(time.time()),
            "currency": "EUR",
        }

        try:
            resp = await self._client.post(
                TOLLGURU_URL,
                json=payload,
                headers={
                    "x-api-key": settings.tollguru_api_key,
                    "Content-Type": "application/json",
                },
            )
        except Exception as exc:
            log.warning("tollguru.request_error", error=str(exc))
            return None

        if resp.status_code != 200:
            log.warning("tollguru.api_error", status=resp.status_code, body=resp.text[:300])
            return None

        data = resp.json()
        log.debug("tollguru.response", data=json.dumps(data)[:500])

        costs = data.get("route", {}).get("costs", {})
        toll = (
            costs.get("tagAndCash")
            or costs.get("cash")
            or costs.get("minimumTollCost")
            or 0.0
        )
        return float(toll)

    def _mem_store(self, key: str, value: float) -> None:
        if key in self._mem:
            self._mem.move_to_end(key)
        else:
            self._mem[key] = value
            if len(self._mem) > _MEM_CACHE_MAX:
                self._mem.popitem(last=False)

    async def aclose(self) -> None:
        await self._client.aclose()


# ── helpers ───────────────────────────────────────────────────────────────────

def _cache_key(coordinates: list[list[float]]) -> str:
    sample = _downsample(coordinates, _SAMPLE_SIZE)
    rounded = [[round(c[0], 4), round(c[1], 4)] for c in sample]
    data = json.dumps(rounded, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def _downsample(coords: list[list[float]], n: int) -> list[list[float]]:
    if len(coords) <= n:
        return coords
    step = len(coords) / n
    return [coords[int(i * step)] for i in range(n)]


async def _db_get(db_path: str, cache_key: str) -> float | None:
    try:
        async with (
            aiosqlite.connect(db_path) as db,
            db.execute("SELECT toll_eur FROM toll_cache WHERE cache_key = ?", (cache_key,)) as cur,
        ):
            row = await cur.fetchone()
            return float(row[0]) if row else None
    except Exception as exc:
        log.warning("tollguru.db_read_error", error=str(exc))
        return None


async def _db_store(db_path: str, cache_key: str, toll_eur: float) -> None:
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO toll_cache "
                "(cache_key, toll_eur, created_at) VALUES (?, ?, ?)",
                (cache_key, toll_eur, int(time.time())),
            )
            await db.commit()
    except Exception as exc:
        log.warning("tollguru.db_write_error", error=str(exc))
