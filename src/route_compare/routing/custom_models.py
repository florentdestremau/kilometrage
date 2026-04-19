"""
Presets d'itinéraires Graphhopper compatibles avec le tier gratuit.

Le tier gratuit ne supporte pas custom_model (mode flexible).
On utilise le paramètre `avoid` (standard) et on recalcule la durée
avec le plafond de vitesse en post-traitement dans main.py.
"""


def max_speed_preset(max_speed: int) -> dict:
    """Itinéraire le plus rapide (généralement par autoroute)."""
    return {}


def avoid_tolls_preset(max_speed: int) -> dict:
    """Évite les routes à péage."""
    return {"avoid": "toll"}


def balanced_preset(max_speed: int) -> dict:
    """Évite les autoroutes — passe par les nationales."""
    return {"avoid": "motorway"}


PRESETS: dict[str, tuple[str, callable]] = {
    "motorway_capped": ("Autoroute plafonnée", max_speed_preset),
    "avoid_tolls": ("Sans péage", avoid_tolls_preset),
    "balanced": ("Via nationales", balanced_preset),
}
