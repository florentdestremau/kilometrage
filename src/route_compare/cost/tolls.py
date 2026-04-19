"""
Estimation des péages par heuristique.

Méthode : somme des km à péage × tarif moyen configurable.
Résultat marqué confidence="estimated" (précision ±20%).

Graphhopper retourne `details.toll` avec des valeurs :
- "NO"   → pas de péage
- "ALL"  → péage tous véhicules
"""

from route_compare.config import settings
from route_compare.models import Segment


def toll_km_and_cost(
    segments: list[Segment],
    rate_eur_per_km: float | None = None,
) -> tuple[float, float]:
    """
    Retourne (km_à_péage, coût_péage_eur).

    rate_eur_per_km : tarif moyen par km, défaut depuis settings.
    """
    rate = rate_eur_per_km if rate_eur_per_km is not None else settings.toll_rate_eur_per_km
    toll_km = sum(s.distance_m / 1000.0 for s in segments if s.has_toll)
    return toll_km, toll_km * rate
