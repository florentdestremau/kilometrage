"""
Presets de custom_model Graphhopper.

Chaque preset définit des règles de vitesse et/ou de priorité appliquées
sur certaines catégories de routes (road_class).

Référence Graphhopper : https://docs.graphhopper.com/latest/custom-models/
"""


def max_speed_preset(max_speed: int) -> dict:
    """Plafonne MOTORWAY et TRUNK à max_speed km/h."""
    return {
        "speed": [
            {
                "if": "road_class == MOTORWAY",
                "limit_to": max_speed,
            },
            {
                "if": "road_class == TRUNK",
                "limit_to": max_speed,
            },
        ]
    }


def avoid_tolls_preset(max_speed: int) -> dict:
    """Évite les routes à péage, plafonne quand même la vitesse."""
    return {
        "speed": [
            {
                "if": "road_class == MOTORWAY",
                "limit_to": max_speed,
            },
            {
                "if": "road_class == TRUNK",
                "limit_to": max_speed,
            },
        ],
        "priority": [
            {
                "if": "toll == ALL",
                "multiply_by": "0",
            },
        ],
    }


def balanced_preset(max_speed: int) -> dict:
    """Plafond vitesse + légère pénalité péages (compromis temps/coût)."""
    return {
        "speed": [
            {
                "if": "road_class == MOTORWAY",
                "limit_to": max_speed,
            },
            {
                "if": "road_class == TRUNK",
                "limit_to": max_speed,
            },
        ],
        "priority": [
            {
                "if": "toll == ALL",
                "multiply_by": "0.8",
            },
        ],
    }


PRESETS: dict[str, tuple[str, callable]] = {
    "motorway_capped": ("Autoroute plafonnée", max_speed_preset),
    "avoid_tolls": ("Sans péage", avoid_tolls_preset),
    "balanced": ("Mixte économique", balanced_preset),
}
