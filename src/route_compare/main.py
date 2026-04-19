"""Point d'entrée FastAPI — Route Compare."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from route_compare.config import settings
from route_compare.cost.fuel import parse_segments_from_path, total_fuel
from route_compare.cost.tolls import toll_km_and_cost
from route_compare.export.deep_links import apple_maps_url, google_maps_url, waze_url
from route_compare.export.waypoints import extract_waypoint_cities
from route_compare.llm.narrator import stream_narration
from route_compare.models import (
    ComparisonResponse,
    Coord,
    CostBreakdown,
    ErrorResponse,
    ExportLinks,
    RouteRequest,
    RouteResult,
)
from route_compare.routing.custom_models import PRESETS
from route_compare.routing.graphhopper import (
    GraphhopperClient,
    GraphhopperError,
    QuotaExceededError,
    RouteNotFoundError,
)

log = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
_gh_client: GraphhopperClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _gh_client
    _gh_client = GraphhopperClient()
    log.info("app.startup")
    yield
    if _gh_client:
        await _gh_client.aclose()
    log.info("app.shutdown")


app = FastAPI(
    title="Route Compare",
    description="Comparateur d'itinéraires avec plafond de vitesse personnalisé",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


@app.get("/up")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/compare",
    response_model=ComparisonResponse,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit("10/minute")
async def compare(request: Request, body: RouteRequest) -> ComparisonResponse:
    gh = _gh_client
    if gh is None:
        raise HTTPException(503, "Service non disponible")

    # Géocodage origine + destination
    try:
        origin_lat, origin_lng = await gh.geocode(body.origin)
        dest_lat, dest_lng = await gh.geocode(body.destination)
    except RouteNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc
    except GraphhopperError as exc:
        raise HTTPException(503, str(exc)) from exc

    origin_coord = Coord(lat=origin_lat, lng=origin_lng)
    dest_coord = Coord(lat=dest_lat, lng=dest_lng)

    # Calcul des 3 presets en parallèle
    preset_tasks = {
        preset_id: gh.route(
            [(origin_lat, origin_lng), (dest_lat, dest_lng)],
            build_fn(body.max_speed),
        )
        for preset_id, (_, build_fn) in PRESETS.items()
    }
    preset_results = await asyncio.gather(*preset_tasks.values(), return_exceptions=True)

    routes: list[RouteResult] = []

    for (preset_id, (label, _)), result in zip(PRESETS.items(), preset_results):
        if isinstance(result, Exception):
            log.warning("preset.failed", preset=preset_id, error=str(result))
            continue

        path = result
        distance_km = path.get("distance", 0) / 1000
        duration_min = path.get("time", 0) / 60_000
        avg_speed = distance_km / (duration_min / 60) if duration_min > 0 else 0

        segments = parse_segments_from_path(path)
        fuel_liters = total_fuel(segments, body.fuel_consumption_l_per_100)
        fuel_eur = fuel_liters * body.fuel_price
        toll_km, toll_eur = toll_km_and_cost(segments)

        # Villes étapes (en parallèle avec les autres presets)
        coords: list[list[float]] = path.get("points", {}).get("coordinates", [])
        waypoints = await extract_waypoint_cities(coords, distance_km)

        # Deep links
        avoid_params = ["tolls"] if preset_id == "avoid_tolls" else None
        export = ExportLinks(
            waze=waze_url(dest_coord),
            google_maps=google_maps_url(origin_coord, dest_coord, avoid=avoid_params),
            apple_maps=apple_maps_url(dest_coord),
        )

        routes.append(
            RouteResult(
                label=label,
                preset=preset_id,
                distance_km=round(distance_km, 1),
                duration_min=round(duration_min, 0),
                avg_speed_kmh=round(avg_speed, 1),
                cost=CostBreakdown(
                    fuel_liters=round(fuel_liters, 2),
                    fuel_eur=round(fuel_eur, 2),
                    toll_eur=round(toll_eur, 2),
                    toll_km=round(toll_km, 1),
                    total_eur=round(fuel_eur + toll_eur, 2),
                ),
                waypoint_cities=waypoints,
                export=export,
                geometry=coords,
            )
        )

    if not routes:
        raise HTTPException(503, "Aucun itinéraire calculé. Vérifiez les adresses saisies.")

    routes.sort(key=lambda r: r.cost.total_eur)

    return ComparisonResponse(
        origin=body.origin,
        destination=body.destination,
        max_speed=body.max_speed,
        routes=routes,
        narrator_available=bool(settings.anthropic_api_key),
    )


@app.get("/narrate")
@limiter.limit("5/minute")
async def narrate(
    request: Request,
    origin: str,
    destination: str,
    max_speed: int = 110,
) -> StreamingResponse:
    """
    SSE endpoint : retourne la narration LLM en streaming.
    Le front appelle cet endpoint séparément après avoir reçu /compare.
    """

    async def event_generator() -> AsyncIterator[str]:
        # On relance un compare light pour avoir les données (ou le front les passe en POST body)
        # Ici on génère juste un SSE vide d'exemple — le vrai flow passe les routes en body
        yield "data: [narrateur indisponible sans données de routes]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/narrate")
@limiter.limit("5/minute")
async def narrate_post(
    request: Request,
    body: ComparisonResponse,
) -> StreamingResponse:
    """SSE : narration des routes déjà calculées."""

    async def event_generator() -> AsyncIterator[str]:
        async for chunk in stream_narration(
            body.routes, body.origin, body.destination, body.max_speed
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Servir les fichiers statiques
import os as _os

_static_dir = _os.path.join(_os.path.dirname(__file__), "static")
if _os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
