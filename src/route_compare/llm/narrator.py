"""
Narration LLM des résultats de comparaison via Claude (streaming SSE).

Fallback vers une phrase templatée si ANTHROPIC_API_KEY est absent.
"""

from collections.abc import AsyncIterator

import structlog

from route_compare.config import settings
from route_compare.models import RouteResult

log = structlog.get_logger()

SYSTEM_PROMPT = """Tu es un copilote de voyage qui compare des itinéraires routiers.
Réponds toujours en français. Maximum 120 mots.
Utilise uniquement les chiffres fournis dans le JSON, sans jamais inventer de données.
Commence directement par ta recommandation (pas de formule de politesse).
Structure : 1) recommandation claire, 2) comparaison chiffrée clé, 3) conseil pratique."""


def _fallback_summary(routes: list[RouteResult], max_speed: int) -> str:
    if not routes:
        return "Aucun itinéraire calculé."
    best = routes[0]
    return (
        f"À {max_speed} km/h, l'itinéraire « {best.label} » est le plus économique "
        f"({best.cost.total_eur:.0f} € — {best.cost.fuel_eur:.0f} € de carburant "
        f"+ {best.cost.toll_eur:.0f} € de péages estimés) "
        f"pour {best.distance_km:.0f} km en {best.duration_min:.0f} min."
    )


async def stream_narration(
    routes: list[RouteResult],
    origin: str,
    destination: str,
    max_speed: int,
) -> AsyncIterator[str]:
    """Génère la narration en streaming. Yields des chunks de texte."""
    if not settings.anthropic_api_key:
        log.warning("narrator.no_api_key", fallback=True)
        yield _fallback_summary(routes, max_speed)
        return

    import anthropic  # import tardif pour éviter l'erreur si pas installé

    routes_json = [
        {
            "label": r.label,
            "distance_km": round(r.distance_km, 1),
            "duration_min": round(r.duration_min),
            "avg_speed_kmh": round(r.avg_speed_kmh, 1),
            "fuel_liters": round(r.cost.fuel_liters, 1),
            "fuel_eur": round(r.cost.fuel_eur, 2),
            "toll_eur": round(r.cost.toll_eur, 2),
            "total_eur": round(r.cost.total_eur, 2),
        }
        for r in routes
    ]

    user_content = (
        f"Trajet : {origin} → {destination}, vitesse max {max_speed} km/h.\n"
        f"Itinéraires calculés (triés par coût) :\n"
        f"{routes_json}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            async for chunk in stream.text_stream:
                yield chunk
    except Exception as exc:
        log.error("narrator.stream_error", error=str(exc))
        yield _fallback_summary(routes, max_speed)
